package com.capstone.mortgage;

import com.capstone.mortgage.controller.MortgageController;
import com.capstone.mortgage.service.MortgageService;
import org.junit.jupiter.api.Test;
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
class DatabaseFailureIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MortgageService mortgageService;

    @Test
    void whenDatabaseFails_thenReturnsGracefulErrorResponse() throws Exception {
        // Simulate a runtime database failure thrown by the service layer
        when(mortgageService.getMortgageById(1L))
                .thenThrow(new DataAccessResourceFailureException("Database connection failed"));

        mockMvc.perform(get("/api/v1/mortgages/1")
                        .header("X-Correlation-ID", "test-db-failure-correlation"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.correlationId").value("test-db-failure-correlation"));
    }
}