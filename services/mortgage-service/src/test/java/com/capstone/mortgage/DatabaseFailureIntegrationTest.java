package com.capstone.mortgage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class DatabaseFailureIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void whenDatabaseIsUnreachable_thenReturnsGracefulErrorResponse() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/1")
                        .header("X-Correlation-ID", "test-db-failure-correlation"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.correlationId").value("test-db-failure-correlation"));
    }
}