package com.capstone.mortgage.security;

import com.capstone.mortgage.controller.AuthController;
import com.capstone.mortgage.controller.MortgageController;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Task 6.3: login throttled per account and per IP; writes throttled per user. Each test uses its own client IP. */
@WebMvcTest(controllers = {AuthController.class, MortgageController.class})
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@TestPropertySource(properties = {
        "app.security.rate-limit.login-per-user-per-minute=2",
        "app.security.rate-limit.login-per-ip-per-minute=4",
        "app.security.rate-limit.writes-per-user-per-minute=2"
})
class RateLimitTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AuthService authService;
    @MockBean
    private MortgageService mortgageService;
    @MockBean
    private PaymentService paymentService;

    @BeforeEach
    void stub() {
        when(authService.login(anyString(), anyString()))
                .thenReturn(new TokenService.IssuedToken("t", 3600, List.of("ADMIN")));
        when(paymentService.processPayment(anyString(), any(Payment.class), any()))
                .thenReturn(new PaymentService.PaymentOutcome(new Payment(), false));
    }

    private static RequestPostProcessor fromIp(String ip) {
        return request -> {
            request.setRemoteAddr(ip);
            return request;
        };
    }

    private static MockHttpServletRequestBuilder login(String username, String ip) {
        return post("/api/v1/auth/login").with(fromIp(ip)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + username + "\",\"password\":\"whatever-123\"}");
    }

    @Test
    void loginIsThrottledPerAccount() throws Exception {
        mockMvc.perform(login("admin@capstone.local", "10.0.0.1")).andExpect(status().isOk());
        mockMvc.perform(login("admin@capstone.local", "10.0.0.1")).andExpect(status().isOk());
        mockMvc.perform(login("admin@capstone.local", "10.0.0.1"))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"))
                .andExpect(jsonPath("$.code").value("RATE_LIMITED"))
                .andExpect(jsonPath("$.correlationId").exists());
        // A different account from the same IP is not blocked by the per-account limit
        mockMvc.perform(login("risk@capstone.local", "10.0.0.1")).andExpect(status().isOk());
    }

    @Test
    void loginIsThrottledPerIpAcrossAccounts() throws Exception {
        for (int i = 0; i < 4; i++) {
            mockMvc.perform(login("user" + i + "@capstone.local", "10.0.0.2")).andExpect(status().isOk());
        }
        mockMvc.perform(login("user9@capstone.local", "10.0.0.2"))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.code").value("RATE_LIMITED"));
        // Another client is unaffected
        mockMvc.perform(login("user9@capstone.local", "10.0.0.3")).andExpect(status().isOk());
    }

    @Test
    void writesAreThrottledPerUser() throws Exception {
        String body = "{\"dueDate\":\"2026-03-01\",\"paidDate\":\"2026-03-02\",\"amount\":1.00,\"status\":\"POSTED\"}";
        for (int i = 0; i < 2; i++) {
            mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments").contentType(MediaType.APPLICATION_JSON).content(body)
                            .with(user("busy-agent@capstone.local").roles("SERVICING_AGENT")))
                    .andExpect(status().isOk());
        }
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments").contentType(MediaType.APPLICATION_JSON).content(body)
                        .with(user("busy-agent@capstone.local").roles("SERVICING_AGENT")))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"));
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments").contentType(MediaType.APPLICATION_JSON).content(body)
                        .with(user("other-agent@capstone.local").roles("SERVICING_AGENT")))
                .andExpect(status().isOk());
    }
}
