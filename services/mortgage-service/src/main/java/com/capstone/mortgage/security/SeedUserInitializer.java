package com.capstone.mortgage.security;

import com.capstone.mortgage.entity.AppUser;
import com.capstone.mortgage.repository.AppUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Creates the five standard seed users (guides/standards.md) on startup when AUTH_SEED_PASSWORD is set and the user
 * does not exist yet. Only the BCrypt hash is stored; the plain password lives in your local .env, never in Git.
 * Existing users are left untouched (change a password by updating the hash, not by re-seeding).
 */
@Component
public class SeedUserInitializer implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(SeedUserInitializer.class);

    static final Map<String, List<String>> SEED_USERS = new LinkedHashMap<>();
    static {
        SEED_USERS.put("admin@capstone.local", List.of("ADMIN"));
        SEED_USERS.put("underwriter@capstone.local", List.of("UNDERWRITER"));
        SEED_USERS.put("servicing@capstone.local", List.of("SERVICING_AGENT"));
        SEED_USERS.put("risk@capstone.local", List.of("RISK_ANALYST"));
        SEED_USERS.put("support@capstone.local", List.of("SUPPORT"));
    }

    private final AppUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final String seedPassword;

    public SeedUserInitializer(AppUserRepository userRepository,
                               PasswordEncoder passwordEncoder,
                               @Value("${app.security.seed-users-password:}") String seedPassword) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.seedPassword = seedPassword;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (seedPassword == null || seedPassword.isBlank()) {
            log.warn("AUTH_SEED_PASSWORD not set: seed users were not created (login only works for existing users)");
            return;
        }
        if (seedPassword.length() < 12) {
            throw new IllegalStateException("AUTH_SEED_PASSWORD must be at least 12 characters");
        }
        int created = 0;
        for (Map.Entry<String, List<String>> entry : SEED_USERS.entrySet()) {
            if (!userRepository.existsByUsernameIgnoreCase(entry.getKey())) {
                userRepository.save(new AppUser(entry.getKey(), passwordEncoder.encode(seedPassword), entry.getValue()));
                created++;
            }
        }
        log.info("Seed users ready ({} created, {} total)", created, SEED_USERS.size());
    }
}
