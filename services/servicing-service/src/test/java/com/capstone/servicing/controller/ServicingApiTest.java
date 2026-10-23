package com.capstone.servicing.controller;

import com.capstone.servicing.dto.DelinquencyResponse;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.exception.ResourceNotFoundException;
import com.capstone.servicing.service.ServicingService;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.capstone.servicing.security.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;
import java.util.Map;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@WithMockUser(username = "servicing@capstone.local", roles = "SERVICING_AGENT")
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
        ServicingHistory history = new ServicingHistory();
        history.setId(UUID.randomUUID());
        history.setMortgageId(UUID.randomUUID());
        history.setEventType("PAYMENT_POSTED");
        history.setDescription("Payment posted");
        history.setEventTime(java.time.Instant.parse("2026-03-02T10:00:00Z"));
        when(servicingService.getServicingHistory("MTG-1001")).thenReturn(Collections.singletonList(history));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mortgageExternalId").value("MTG-1001"))
                .andExpect(jsonPath("$.events[0].eventType").value("PAYMENT_POSTED"))
                .andExpect(jsonPath("$.events[0].mortgageId").doesNotExist());
    }

    // --- Minimum Test Case: GET /api/v1/mortgages/{id}/delinquency ---
    @Test
    void getDelinquency_Returns200WithDelinquencyMetrics() throws Exception {
        when(servicingService.getDelinquencyStatus("MTG-1002")).thenReturn(
                new DelinquencyResponse("MTG-1002", "DELINQUENT", "2026-01-10", 45, "MODERATE"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-1002/delinquency")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mortgageExternalId").value("MTG-1002"))
                .andExpect(jsonPath("$.status").value("DELINQUENT"))
                .andExpect(jsonPath("$.delinquentSince").value("2026-01-10"))
                .andExpect(jsonPath("$.daysPastDue").value(45))
                .andExpect(jsonPath("$.severity").value("MODERATE"));
    }

    @Test
    void getServicingHistory_UnknownMortgage_Returns404WithErrorEnvelope() throws Exception {
        when(servicingService.getServicingHistory("MTG-9999")).thenThrow(ResourceNotFoundException.mortgage("MTG-9999"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-9999/servicing-history")
                        .header("X-Correlation-Id", "7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("MORTGAGE_NOT_FOUND"))
                .andExpect(jsonPath("$.correlationId").value("7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .andExpect(jsonPath("$.timestamp").exists());
    }

    @Test
    void createServicingEvent_InvalidEventType_Returns400() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/servicing-events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventType\":\"bad type\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    // --- Additional Endpoint Test: POST /api/v1/mortgages/{id}/servicing-events ---
    @Test
    void createServicingEvent_Returns201() throws Exception {
        ServicingHistory mockHistory = new ServicingHistory();
        mockHistory.setId(UUID.randomUUID());
        mockHistory.setEventType("PAYMENT_RECEIVED");
        mockHistory.setDescription("Standard monthly payment processed");

        when(servicingService.createServicingEvent(eq("MTG-1001"), any(String.class), any(String.class)))
                .thenReturn(mockHistory);

        Map<String, String> payload = Map.of(
                "eventType", "PAYMENT_RECEIVED",
                "description", "Standard monthly payment processed"
        );

        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/servicing-events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.eventType").value("PAYMENT_RECEIVED"))
                .andExpect(jsonPath("$.mortgageId").doesNotExist());
    }
}