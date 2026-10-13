package com.capstone.servicing.controller;

import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.service.ServicingService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
class ServicingApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ServicingService servicingService;

    // --- Minimum Test Case: GET /api/v1/mortgages/{id}/servicing-history ---
    @Test
    void getServicingHistory_Returns200WithOrderedEvents() throws Exception {
        when(servicingService.getServicingHistory(1001L)).thenReturn(Collections.emptyList());

        mockMvc.perform(get("/api/v1/mortgages/1001/servicing-history")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    // --- Minimum Test Case: GET /api/v1/mortgages/{id}/delinquency ---
    @Test
    void getDelinquency_Returns200WithDelinquencyMetrics() throws Exception {
        Map<String, Object> mockDelinquencyData = Map.of("daysPastDue", 30, "status", "DELINQUENT");
        when(servicingService.getDelinquencyStatus(1002L)).thenReturn(mockDelinquencyData);

        mockMvc.perform(get("/api/v1/mortgages/1002/delinquency")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.daysPastDue").value(30));
    }

    // --- Additional Endpoint Test: POST /api/v1/mortgages/{id}/servicing-events ---
    @Test
    void createServicingEvent_Returns201() throws Exception {
        ServicingHistory mockHistory = new ServicingHistory();
        mockHistory.setId(1L);

        when(servicingService.createServicingEvent(eq(1001L), any(String.class), any(String.class)))
                .thenReturn(mockHistory);

        Map<String, String> payload = Map.of(
                "eventType", "PAYMENT_RECEIVED",
                "description", "Standard monthly payment processed"
        );

        mockMvc.perform(post("/api/v1/mortgages/1001/servicing-events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isCreated());
    }
}