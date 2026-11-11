package com.capstone.mortgage.security;

import com.capstone.mortgage.entity.AppUser;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.repository.AppUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Optional;

/**
 * Username/password login against app_user (BCrypt). Unknown user, wrong password and disabled account all return
 * the same 401 so the API does not reveal which usernames exist; a dummy hash is checked for unknown users to keep
 * timing similar. Passwords and tokens are never logged.
 */
@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);

    private final AppUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final TokenService tokenService;
    private final String dummyHash;

    public AuthService(AppUserRepository userRepository, PasswordEncoder passwordEncoder, TokenService tokenService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.tokenService = tokenService;
        this.dummyHash = passwordEncoder.encode("timing-equalizer-not-a-real-password");
    }

    @Transactional(readOnly = true)
    public TokenService.IssuedToken login(String username, String password) {
        Optional<AppUser> user = userRepository.findByUsernameIgnoreCase(username.trim());
        boolean passwordMatches = passwordEncoder.matches(password, user.map(AppUser::getPasswordHash).orElse(dummyHash));

        if (user.isEmpty() || !passwordMatches || !user.get().isEnabled()) {
            log.warn("Failed login attempt for username={}", sanitize(username));
            throw new BusinessRuleException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid username or password");
        }
        log.info("Successful login for username={}", user.get().getUsername());
        return tokenService.issue(user.get().getUsername(), user.get().roleList());
    }

    /** Prevent log forging via CR/LF in user-supplied usernames. */
    private static String sanitize(String value) {
        String cleaned = value.replaceAll("[\\r\\n\\t]", "_").trim();
        return cleaned.length() > 100 ? cleaned.substring(0, 100) : cleaned;
    }
}
