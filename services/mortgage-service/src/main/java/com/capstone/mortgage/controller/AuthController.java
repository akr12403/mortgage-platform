package com.capstone.mortgage.controller;

import com.capstone.mortgage.dto.LoginRequest;
import com.capstone.mortgage.dto.LoginResponse;
import com.capstone.mortgage.security.AuthService;
import com.capstone.mortgage.security.RateLimitExceededException;
import com.capstone.mortgage.security.RateLimitProperties;
import com.capstone.mortgage.security.RateLimiter;
import com.capstone.mortgage.security.TokenService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthService authService;
    private final RateLimiter rateLimiter;
    private final RateLimitProperties rateLimitProperties;

    public AuthController(AuthService authService, RateLimiter rateLimiter, RateLimitProperties rateLimitProperties) {
        this.authService = authService;
        this.rateLimiter = rateLimiter;
        this.rateLimitProperties = rateLimitProperties;
    }

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request, HttpServletRequest http) {
        // Task 6.3: per-account brute-force throttle (the per-IP limit is applied earlier in RateLimitFilter)
        if (rateLimitProperties.enabled()) {
            RateLimiter.Decision decision = rateLimiter.tryAcquire(
                    "login-user:" + http.getRemoteAddr() + ":" + request.username().trim().toLowerCase(),
                    rateLimitProperties.loginPerUserPerMinute(), java.time.Duration.ofMinutes(1));
            if (!decision.allowed()) {
                throw new RateLimitExceededException(decision.retryAfterSeconds());
            }
        }
        TokenService.IssuedToken token = authService.login(request.username(), request.password());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new LoginResponse(token.accessToken(), "Bearer", token.expiresInSeconds(), token.roles()));
    }
}
