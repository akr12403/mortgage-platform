package com.capstone.servicing.controller;

import com.capstone.servicing.security.SecurityConfig;
import com.capstone.servicing.service.ServicingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.CannotCreateTransactionException;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** M9 RCA 2026-11-10 (B-22): a database outage is a temporary 503 with Retry-After, not a generic 500. */
@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@WithMockUser(username = "servicing@capstone.local", roles = "SERVICING_AGENT")
class DatabaseUnavailableTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ServicingService servicingService;

    @Test
    void noConnectionFromThePool_returns503WithRetryAfter() throws Exception {
        when(servicingService.getServicingHistory("MTG-1001"))
                .thenThrow(new CannotCreateTransactionException("Could not open JPA EntityManager for transaction"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history").header("X-Correlation-ID", "db-down-1"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(header().string("Retry-After", "5"))
                .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"))
                .andExpect(jsonPath("$.correlationId").value("db-down-1"));
    }

    @Test
    void connectionLost_returns503() throws Exception {
        when(servicingService.getDelinquencyStatus("MTG-1001"))
                .thenThrow(new DataAccessResourceFailureException("Connection refused"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/delinquency"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"));
    }
}
