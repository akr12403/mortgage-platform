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
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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

    @Test
    void whenDatabaseFails_thenReturnsGracefulErrorResponse() throws Exception {
        // Simulate a database connection failure thrown when fetching a mortgage
        when(mortgageService.getMortgageById("MTG-1001"))
                .thenThrow(new DataAccessResourceFailureException("Database connection lost"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001")
                        .header("X-Correlation-ID", "test-db-failure-correlation"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.correlationId").value("test-db-failure-correlation"));
    }
}