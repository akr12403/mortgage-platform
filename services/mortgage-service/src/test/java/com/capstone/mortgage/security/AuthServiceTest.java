package com.capstone.mortgage.security;

import com.capstone.mortgage.entity.AppUser;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.repository.AppUserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.*;

class AuthServiceTest {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4); // low cost keeps the test fast
    private final AppUserRepository repository = mock(AppUserRepository.class);
    private final TokenService tokenService = mock(TokenService.class);
    private final AuthService authService = new AuthService(repository, encoder, tokenService);

    private AppUser user(boolean enabled) {
        AppUser user = new AppUser("servicing@capstone.local", encoder.encode("correct-horse-battery"), List.of("SERVICING_AGENT"));
        user.setEnabled(enabled);
        return user;
    }

    @Test
    void correctPassword_IssuesTokenWithRoles() {
        when(repository.findByUsernameIgnoreCase("servicing@capstone.local")).thenReturn(Optional.of(user(true)));
        when(tokenService.issue("servicing@capstone.local", List.of("SERVICING_AGENT")))
                .thenReturn(new TokenService.IssuedToken("t", 3600, List.of("SERVICING_AGENT")));

        assertThat(authService.login("servicing@capstone.local", "correct-horse-battery").accessToken()).isEqualTo("t");
    }

    @Test
    void wrongPassword_UnknownUser_AndDisabledUser_AllGiveTheSame401() {
        when(repository.findByUsernameIgnoreCase("servicing@capstone.local")).thenReturn(Optional.of(user(true)));
        when(repository.findByUsernameIgnoreCase("nobody@capstone.local")).thenReturn(Optional.empty());
        when(repository.findByUsernameIgnoreCase("disabled@capstone.local")).thenReturn(Optional.of(user(false)));

        for (String[] attempt : new String[][]{
                {"servicing@capstone.local", "wrong"},
                {"nobody@capstone.local", "correct-horse-battery"},
                {"disabled@capstone.local", "correct-horse-battery"}}) {
            assertThatThrownBy(() -> authService.login(attempt[0], attempt[1]))
                    .isInstanceOf(BusinessRuleException.class)
                    .hasMessage("Invalid username or password");
        }
        verify(tokenService, never()).issue(any(), anyList());
    }

    @Test
    void passwordsAreStoredAsBcryptHashes() {
        AppUser stored = user(true);
        assertThat(stored.getPasswordHash()).startsWith("$2a$").doesNotContain("correct-horse-battery");
    }
}
