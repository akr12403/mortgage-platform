package com.capstone.mortgage.security;

import com.capstone.mortgage.controller.AuthController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

/** Task 6.3: baseline security headers on every response, including errors. */
@WebMvcTest(AuthController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
class SecurityHeadersTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AuthService authService;

    @Test
    void errorResponsesCarryTheSecurityHeaders() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001"))   // 401, still hardened
                .andExpect(header().string("Content-Security-Policy", SecurityHeaders.CONTENT_SECURITY_POLICY))
                .andExpect(header().string("Permissions-Policy", SecurityHeaders.PERMISSIONS_POLICY))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(header().string("X-Frame-Options", "DENY"))
                .andExpect(header().string("Referrer-Policy", "no-referrer"))
                .andExpect(header().string("Cross-Origin-Resource-Policy", "same-origin"))
                .andExpect(header().string("Cache-Control", containsString("no-store")));
    }

    @Test
    void hstsOnlyOverHttps() throws Exception {
        mockMvc.perform(post("/api/v1/auth/login").secure(true).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(header().string("Strict-Transport-Security", containsString("max-age=31536000")));
        mockMvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }
}
