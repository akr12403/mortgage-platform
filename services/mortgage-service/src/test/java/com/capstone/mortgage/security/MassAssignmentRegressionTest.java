package com.capstone.mortgage.security;

import com.capstone.mortgage.controller.MortgageController;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Regression test for VULN-M6-001 (Task 6.3, OWASP API3 "mass assignment"), found in the M6 review:
 * POST /api/v1/mortgages/{id}/payments bound the request body straight onto the Payment JPA entity. Sending
 * "id" of an existing payment made JPA merge (overwrite) that payment — e.g. turning someone's FAILED payment
 * into POSTED or changing its amount. Fixed by binding to PaymentRequest, which has no id/mortgage fields.
 */
@WebMvcTest(MortgageController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@WithMockUser(username = "servicing@capstone.local", roles = "SERVICING_AGENT")
class MassAssignmentRegressionTest {

    private static final String EXISTING_PAYMENT_ID = "11111111-2222-3333-4444-555555555555";

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MortgageService mortgageService;

    @MockBean
    private PaymentService paymentService;

    @Test
    void clientSuppliedIdAndMortgageAreIgnored_PaymentIsAlwaysNew() throws Exception {
        Payment stored = new Payment();
        stored.setStatus("POSTED");
        when(paymentService.processPayment(eq("MTG-1001"), any(Payment.class), isNull()))
                .thenReturn(new PaymentService.PaymentOutcome(stored, false));

        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"id":"%s",
                                 "mortgage":{"id":"99999999-0000-0000-0000-000000000000","mortgageExternalId":"MTG-1002"},
                                 "dueDate":"2026-03-01","paidDate":"2026-03-02","amount":1850.00,"status":"POSTED"}
                                """.formatted(EXISTING_PAYMENT_ID)))
                .andExpect(status().isOk());

        ArgumentCaptor<Payment> captor = ArgumentCaptor.forClass(Payment.class);
        verify(paymentService).processPayment(eq("MTG-1001"), captor.capture(), isNull());
        Payment bound = captor.getValue();
        assertThat(bound.getId()).as("client must not choose the payment id (would overwrite an existing row)").isNull();
        assertThat(bound.getMortgage()).as("mortgage comes only from the URL").isNull();
        assertThat(bound.getAmount()).isEqualByComparingTo("1850.00");
    }

    @Test
    void amountWithMoreThanTwoDecimals_IsRejected() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"dueDate\":\"2026-03-01\",\"paidDate\":\"2026-03-02\",\"amount\":10.001,\"status\":\"POSTED\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
        verify(paymentService, never()).processPayment(any(), any(), any());
    }

    @Test
    void absurdAmount_IsRejected() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"dueDate\":\"2026-03-01\",\"paidDate\":\"2026-03-02\",\"amount\":99999999999.00,\"status\":\"POSTED\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void oversizedIdempotencyKey_IsRejected() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Idempotency-Key", "k".repeat(256))
                        .content("{\"dueDate\":\"2026-03-01\",\"paidDate\":\"2026-03-02\",\"amount\":1.00,\"status\":\"POSTED\"}"))
                .andExpect(status().isBadRequest());
    }
}
