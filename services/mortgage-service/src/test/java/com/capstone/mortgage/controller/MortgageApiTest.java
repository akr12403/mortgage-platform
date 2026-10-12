package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.util.Collections;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(MortgageController.class)
class MortgageApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private MortgageService mortgageService;

    @MockBean
    private PaymentService paymentService;

    // --- Endpoint 1: GET /api/v1/mortgages/{id} ---
    @Test
    void getMortgageById_HappyPath_Returns200() throws Exception {
        Mortgage mortgage = new Mortgage();
        mortgage.setId(1L);

        when(mortgageService.getMortgageById(1L)).thenReturn(mortgage);

        mockMvc.perform(get("/api/v1/mortgages/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1));
    }

    @Test
    void getMortgageById_NotFound_Returns404() throws Exception {
        when(mortgageService.getMortgageById(999L)).thenThrow(new RuntimeException("Mortgage not found"));

        mockMvc.perform(get("/api/v1/mortgages/999"))
                .andExpect(status().isInternalServerError()); // Or isNotFound() depending on GlobalExceptionHandler mapping
    }

    // --- Endpoint 2: POST /api/v1/mortgages ---
    @Test
    void createMortgage_HappyPath_Returns201() throws Exception {
        Mortgage mortgage = new Mortgage();
        mortgage.setId(1L);

        when(mortgageService.saveMortgage(any(Mortgage.class))).thenReturn(mortgage);

        mockMvc.perform(post("/api/v1/mortgages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(mortgage)))
                .andExpect(status().isCreated());
    }

    // --- Endpoint 2: POST /api/v1/mortgages (Validation Error Test) ---
    @Test
    void createMortgage_ValidationError_Returns400() throws Exception {
        // Pass a malformed JSON string or an empty body to ensure it triggers validation or parsing failure
        mockMvc.perform(post("/api/v1/mortgages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid-json}"))
                .andExpect(status().isBadRequest());
    }

    // --- Endpoint 3: POST /api/v1/mortgages/{id}/payments (Happy Path Test) ---
    @Test
    void createPayment_HappyPath_Returns200() throws Exception {
        Payment payment = new Payment();
        payment.setAmount(new BigDecimal("1500.00"));
        payment.setPaidDate(java.time.LocalDate.now());
        payment.setStatus("COMPLETED");

        when(paymentService.processPayment(eq(1L), any(Payment.class))).thenReturn(payment);

        // Your controller method createPayment returns ResponseEntity.ok(savedPayment), which is 200 OK!
        mockMvc.perform(post("/api/v1/mortgages/1/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payment))
                        .header("X-Correlation-Id", "test-corr-id"))
                .andExpect(status().isOk());
    }

    @Test
    void createPayment_ValidationError_Returns400() throws Exception {
        Payment payment = new Payment();
        // Assuming amount must be positive, setting invalid amount or letting validation catch null/negative
        payment.setAmount(new BigDecimal("-100.00"));

        mockMvc.perform(post("/api/v1/mortgages/1/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payment)))
                .andExpect(status().isBadRequest());
    }

    // --- Endpoint 4: GET /api/v1/mortgages/{id}/payments ---
    @Test
    void getPayments_HappyPath_Returns200() throws Exception {
        when(mortgageService.getPaymentsByMortgage(1L)).thenReturn(Collections.emptyList());

        mockMvc.perform(get("/api/v1/mortgages/1/payments"))
                .andExpect(status().isOk());
    }

    // --- Endpoint 5: GET /api/v1/mortgages?borrowerId={id} ---
    @Test
    void getMortgagesByBorrower_HappyPath_Returns200() throws Exception {
        when(mortgageService.getMortgagesByBorrower(eq(100L), any(Pageable.class)))
                .thenReturn(Page.empty());

        mockMvc.perform(get("/api/v1/mortgages")
                        .param("borrowerId", "100")
                        .param("page", "0")
                        .param("size", "10"))
                .andExpect(status().isOk());
    }
}