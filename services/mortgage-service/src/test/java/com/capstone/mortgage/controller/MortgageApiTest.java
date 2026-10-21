package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.exception.ResourceNotFoundException;
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
import static org.mockito.ArgumentMatchers.isNull;
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

        when(paymentService.processPayment(eq("MTG-1001"), any(Payment.class), isNull()))
                .thenReturn(new PaymentService.PaymentOutcome(payment, false));

        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payment))
                        .header("X-Correlation-Id", "7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Correlation-ID", "7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .andExpect(header().string("Idempotent-Replayed", "false"));
    }

    @Test
    void createPayment_IdempotencyReplay_ReturnsOriginalWithReplayHeader() throws Exception {
        Payment payment = new Payment();
        payment.setAmount(new BigDecimal("1850.00"));
        payment.setPaidDate(LocalDate.parse("2026-03-02"));
        payment.setDueDate(LocalDate.parse("2026-03-01"));
        payment.setStatus("POSTED");

        when(paymentService.processPayment(eq("MTG-1001"), any(Payment.class), eq("pay-MTG-1001-2026-03-01")))
                .thenReturn(new PaymentService.PaymentOutcome(payment, true));

        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Idempotency-Key", "pay-MTG-1001-2026-03-01")
                        .content(objectMapper.writeValueAsString(payment)))
                .andExpect(status().isOk())
                .andExpect(header().string("Idempotent-Replayed", "true"));
    }

    @Test
    void createPayment_IdempotencyKeyReusedWithDifferentBody_Returns409() throws Exception {
        when(paymentService.processPayment(eq("MTG-1001"), any(Payment.class), eq("pay-key-1")))
                .thenThrow(BusinessRuleException.conflict("IDEMPOTENCY_KEY_REUSED", "Idempotency-Key pay-key-1 was already used"));

        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Idempotency-Key", "pay-key-1")
                        .content("""
                                {"dueDate":"2026-03-01","paidDate":"2026-03-02","amount":1850.00,"status":"POSTED"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("IDEMPOTENCY_KEY_REUSED"))
                .andExpect(jsonPath("$.correlationId").exists())
                .andExpect(jsonPath("$.timestamp").exists());
    }

    // --- Approval workflow stub: POST /api/v1/mortgages/{id}/underwriting-decision ---
    @Test
    void recordUnderwritingDecision_Approved_Returns200() throws Exception {
        Mortgage mortgage = new Mortgage();
        mortgage.setMortgageExternalId("MTG-1010");
        mortgage.setStatus("ACTIVE");
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId("BOR-001");
        mortgage.setBorrower(borrower);
        when(mortgageService.recordUnderwritingDecision("MTG-1010", "APPROVED", "UNDERWRITER")).thenReturn(mortgage);

        mockMvc.perform(post("/api/v1/mortgages/MTG-1010/underwriting-decision")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"APPROVED\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    void recordUnderwritingDecision_InvalidDecision_Returns400() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages/MTG-1010/underwriting-decision")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"MAYBE\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void createMortgage_InvalidBusinessIdFormat_Returns400() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"mortgageExternalId":"MORTGAGE-1","borrowerExternalId":"BOR-001",
                                 "originalAmount":320000.00,"outstandingBalance":318500.00,"originationDate":"2025-06-01"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void createMortgage_Duplicate_Returns409() throws Exception {
        when(mortgageService.saveMortgage(any(MortgageCreateRequest.class)))
                .thenThrow(BusinessRuleException.conflict("MORTGAGE_ALREADY_EXISTS", "Mortgage MTG-1001 already exists"));

        mockMvc.perform(post("/api/v1/mortgages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"mortgageExternalId":"MTG-1001","borrowerExternalId":"BOR-001",
                                 "originalAmount":320000.00,"outstandingBalance":318500.00,"originationDate":"2025-06-01"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("MORTGAGE_ALREADY_EXISTS"));
    }

    @Test
    void getMortgageById_UnknownMortgage_UsesMortgageNotFoundCode() throws Exception {
        when(mortgageService.getMortgageById("MTG-9999")).thenThrow(ResourceNotFoundException.mortgage("MTG-9999"));

        mockMvc.perform(get("/api/v1/mortgages/MTG-9999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("MORTGAGE_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value("Mortgage MTG-9999 was not found"));
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