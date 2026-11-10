package com.capstone.mortgage;

import com.capstone.mortgage.controller.MortgageController;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import com.capstone.mortgage.security.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(MortgageController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@WithMockUser(username = "admin@capstone.local", roles = "ADMIN")
class DatabaseFailureIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MortgageService mortgageService;

    @MockBean
    private PaymentService paymentService;

    // M9 RCA 2026-11-10 (B-22): a database outage is a temporary 503 with Retry-After, not a generic 500.
    @Test
    void whenDatabaseFails_thenReturnsGracefulErrorResponse() throws Exception {
        // Simulate a database connection failure thrown when fetching a mortgage
        when(mortgageService.getMortgageById("MTG-1001"))
                .thenThrow(new DataAccessResourceFailureException("Database connection lost"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001")
                        .header("X-Correlation-ID", "test-db-failure-correlation"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(header().string("Retry-After", "5"))
                .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"))
                .andExpect(jsonPath("$.correlationId").value("test-db-failure-correlation"));
    }

    /** What the drill produced: the connection pool cannot open a connection when a transaction starts. */
    @Test
    void whenNoConnectionCanBeObtained_thenReturns503() throws Exception {
        when(mortgageService.getMortgageById("MTG-1001"))
                .thenThrow(new CannotCreateTransactionException("Could not open JPA EntityManager for transaction",
                        new java.sql.SQLTransientConnectionException(
                                "HikariPool-1 - Connection is not available, request timed out after 3000ms")));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(header().string("Retry-After", "5"))
                .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"))
                .andExpect(jsonPath("$.message").value("The service is temporarily unavailable, please retry"));
    }
}