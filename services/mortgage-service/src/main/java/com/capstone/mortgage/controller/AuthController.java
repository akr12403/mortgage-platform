package com.capstone.mortgage.controller;

import com.capstone.mortgage.dto.LoginRequest;
import com.capstone.mortgage.dto.LoginResponse;
import com.capstone.mortgage.security.AuthService;
import com.capstone.mortgage.security.TokenService;
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

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        TokenService.IssuedToken token = authService.login(request.username(), request.password());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new LoginResponse(token.accessToken(), "Bearer", token.expiresInSeconds(), token.roles()));
    }
}
