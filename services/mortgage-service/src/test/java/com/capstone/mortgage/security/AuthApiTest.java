package com.capstone.mortgage.security;

import com.capstone.mortgage.controller.AuthController;
import com.capstone.mortgage.exception.BusinessRuleException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** POST /api/v1/auth/login is public and returns the reference contract; failures use the error envelope. */
@WebMvcTest(AuthController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
class AuthApiTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AuthService authService;

    @Test
    void login_ValidCredentials_ReturnsTokenWithoutAuthHeader() throws Exception {
        when(authService.login("servicing@capstone.local", "correct-horse-battery"))
                .thenReturn(new TokenService.IssuedToken("header.payload.signature", 3600, List.of("SERVICING_AGENT")));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"servicing@capstone.local\",\"password\":\"correct-horse-battery\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("no-store")))
                .andExpect(jsonPath("$.accessToken").value("header.payload.signature"))
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.expiresInSeconds").value(3600))
                .andExpect(jsonPath("$.roles[0]").value("SERVICING_AGENT"));
    }

    @Test
    void login_BadCredentials_Returns401Envelope() throws Exception {
        when(authService.login("servicing@capstone.local", "wrong-password"))
                .thenThrow(new BusinessRuleException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid username or password"));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"servicing@capstone.local\",\"password\":\"wrong-password\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_CREDENTIALS"))
                .andExpect(jsonPath("$.correlationId").exists())
                .andExpect(jsonPath("$.timestamp").exists());
    }

    @Test
    void login_MissingPassword_Returns400() throws Exception {
        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"servicing@capstone.local\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }
}
