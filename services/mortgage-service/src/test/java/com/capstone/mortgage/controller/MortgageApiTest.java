package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.dto.MortgageCreateRequest;
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
import java.time.LocalDate;
import java.util.Collections;
import java.util.UUID;

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
        mortgage.setId(UUID.randomUUID());
        mortgage.setMortgageExternalId("MTG-1001");
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId("BOR-001");
        mortgage.setBorrower(borrower);
        when(mortgageService.getMortgageById("MTG-1001")).thenReturn(mortgage);

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mortgageExternalId").value("MTG-1001"));
    }

    // --- Updated Endpoint 1: GET unknown mortgage (Expects 404) ---
    @Test
    void getMortgageById_NotFound_Returns404() throws Exception {
        // Maps to the minimum test case: GET unknown mortgage -> 404
        when(mortgageService.getMortgageById("MTG-9999"))
                .thenThrow(new jakarta.persistence.EntityNotFoundException("Mortgage not found"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-9999"))
                .andExpect(status().isNotFound());
    }

    // --- Endpoint 2: POST /api/v1/mortgages ---
    @Test
    void createMortgage_HappyPath_Returns201() throws Exception {
        Mortgage mortgage = new Mortgage();
        mortgage.setId(UUID.randomUUID());
        mortgage.setMortgageExternalId("MTG-1010");
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId("BOR-001");
        mortgage.setBorrower(borrower);
                                when(mortgageService.saveMortgage(any(MortgageCreateRequest.class))).thenReturn(mortgage);

        mockMvc.perform(post("/api/v1/mortgages")
                        .contentType(MediaType.APPLICATION_JSON)
                                                                                                .content("""
                                                                                                                                {
                                                                                                                                        "mortgageExternalId": "MTG-1010",
                                                                                                                                        "borrowerExternalId": "BOR-001",
                                                                                                                                        "originalAmount": 320000.00,
                                                                                                                                        "outstandingBalance": 318500.00,
                                                                                                                                        "originationDate": "2025-06-01",
                                                                                                                                        "loan": {
                                                                                                                                                "loanExternalId": "LOAN-2010",
                                                                                                                                                "interestRate": 0.0650,
                                                                                                                                                "termMonths": 360,
                                                                                                                                                "underwritingDecision": "APPROVED"
                                                                                                                                        }
                                                                                                                                }
                                                                                                                                """))
                .andExpect(status().isCreated());
    }

    // --- Endpoint 3: POST /api/v1/mortgages/{id}/payments ---
    @Test
    void createPayment_HappyPath_Returns200() throws Exception {
        Payment payment = new Payment();
        payment.setAmount(new BigDecimal("1500.00"));
        payment.setPaidDate(LocalDate.now());
        payment.setDueDate(LocalDate.now());
        payment.setStatus("POSTED");

        when(paymentService.processPayment(eq("MTG-1001"), any(Payment.class))).thenReturn(payment);

        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payment))
                        .header("X-Correlation-Id", "test-corr-id"))
                .andExpect(status().isOk());
    }

    @Test
    void createPayment_ValidationError_Returns400() throws Exception {
        // Sending an empty payment body triggers validation for mandatory fields (paidDate, status)
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.correlationId").exists());
    }

    // --- Endpoint 4: GET /api/v1/mortgages/{id}/payments ---
    @Test
    void getPayments_HappyPath_Returns200() throws Exception {
        when(mortgageService.getPaymentsByMortgage("MTG-1001")).thenReturn(Collections.emptyList());

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/payments"))
                .andExpect(status().isOk());
    }

    // --- Endpoint 5: GET /api/v1/mortgages?borrowerId={id} ---
    @Test
    void getMortgagesByBorrower_HappyPath_Returns200() throws Exception {
        when(mortgageService.getMortgagesByBorrower(eq("BOR-001"), any(Pageable.class)))
                .thenReturn(Page.empty());

        mockMvc.perform(get("/api/v1/mortgages")
                        .param("borrowerId", "BOR-001")
                        .param("page", "0")
                        .param("size", "10"))
                .andExpect(status().isOk());
    }
}