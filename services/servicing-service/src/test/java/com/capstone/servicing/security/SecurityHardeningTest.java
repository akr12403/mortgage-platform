package com.capstone.servicing.security;

import com.capstone.servicing.controller.ServicingController;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.service.ServicingService;
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

import java.time.Instant;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Task 6.3: security headers and per-user write throttling on servicing-service. */
@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@TestPropertySource(properties = "app.security.rate-limit.writes-per-user-per-minute=2")
class SecurityHardeningTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ServicingService servicingService;

    @Test
    void responsesCarryTheSecurityHeaders() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history"))   // 401, still hardened
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("Content-Security-Policy", SecurityHeaders.CONTENT_SECURITY_POLICY))
                .andExpect(header().string("Permissions-Policy", SecurityHeaders.PERMISSIONS_POLICY))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(header().string("X-Frame-Options", "DENY"))
                .andExpect(header().string("Cross-Origin-Resource-Policy", "same-origin"));
    }

    private static MockHttpServletRequestBuilder note(String username) {
        return post("/api/v1/mortgages/MTG-1001/servicing-events")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"eventType\":\"ESCROW_ANALYSIS\",\"description\":\"Annual escrow review\"}")
                .with(user(username).roles(Rbac.SERVICING_AGENT));
    }

    @Test
    void writesAreThrottledPerUser() throws Exception {
        ServicingHistory saved = new ServicingHistory();
        saved.setEventType("ESCROW_ANALYSIS");
        saved.setEventTime(Instant.now());
        when(servicingService.createServicingEvent(anyString(), anyString(), anyString())).thenReturn(saved);

        mockMvc.perform(note("busy-agent@capstone.local")).andExpect(status().is2xxSuccessful());
        mockMvc.perform(note("busy-agent@capstone.local")).andExpect(status().is2xxSuccessful());
        mockMvc.perform(note("busy-agent@capstone.local"))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"))
                .andExpect(jsonPath("$.code").value("RATE_LIMITED"));
        mockMvc.perform(note("other-agent@capstone.local")).andExpect(status().is2xxSuccessful());
    }
}
