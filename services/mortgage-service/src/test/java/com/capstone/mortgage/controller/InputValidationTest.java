package com.capstone.mortgage.controller;

import com.capstone.mortgage.exception.ResourceNotFoundException;
import com.capstone.mortgage.repository.BorrowerRepository;
import com.capstone.mortgage.security.SecurityConfig;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Task 6.3: bean validation on every POST body + bounded pagination (OWASP API4). */
@WebMvcTest(controllers = {MortgageController.class, BorrowerController.class})
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@WithMockUser(username = "admin@capstone.local", roles = "ADMIN")
class InputValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MortgageService mortgageService;
    @MockBean
    private PaymentService paymentService;
    @MockBean
    private BorrowerRepository borrowerRepository;

    private static String mortgage(String original, String outstanding, String origination, String rate, int term) {
        return """
                {"mortgageExternalId":"MTG-1010","borrowerExternalId":"BOR-001","originalAmount":%s,
                 "outstandingBalance":%s,"originationDate":"%s",
                 "loan":{"loanExternalId":"LOAN-2010","interestRate":%s,"termMonths":%d,"underwritingDecision":"PENDING"}}
                """.formatted(original, outstanding, origination, rate, term);
    }

    @ParameterizedTest(name = "invalid mortgage #{index}")
    @ValueSource(strings = {
            "BALANCE_ABOVE_ORIGINAL", "FUTURE_ORIGINATION", "RATE_TOO_HIGH", "TERM_TOO_LONG", "TOO_MANY_DECIMALS"})
    void invalidMortgagesAreRejected(String scenario) throws Exception {
        String body = switch (scenario) {
            case "BALANCE_ABOVE_ORIGINAL" -> mortgage("1000.00", "2000.00", "2025-06-01", "0.065", 360);
            case "FUTURE_ORIGINATION" -> mortgage("1000.00", "1000.00", "2999-01-01", "0.065", 360);
            case "RATE_TOO_HIGH" -> mortgage("1000.00", "1000.00", "2025-06-01", "6.5", 360);
            case "TERM_TOO_LONG" -> mortgage("1000.00", "1000.00", "2025-06-01", "0.065", 600);
            default -> mortgage("1000.001", "1000.00", "2025-06-01", "0.065", 360);
        };
        mockMvc.perform(post("/api/v1/mortgages").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void borrowerFieldsAreBounded() throws Exception {
        mockMvc.perform(post("/api/v1/borrowers").contentType(MediaType.APPLICATION_JSON).content("""
                        {"borrowerExternalId":"BOR-010","firstName":"%s","lastName":"R","email":"a@b.test"}
                        """.formatted("x".repeat(101))))
                .andExpect(status().isBadRequest());
        mockMvc.perform(post("/api/v1/borrowers").contentType(MediaType.APPLICATION_JSON).content("""
                        {"borrowerExternalId":"BOR-010","firstName":"A","lastName":"R","email":"a@b.test","phone":"<script>"}
                        """))
                .andExpect(status().isBadRequest());
    }

    @ParameterizedTest
    @ValueSource(strings = {"size=0", "size=101", "size=100000000", "page=-1"})
    void pageSizeIsBounded(String query) throws Exception {
        mockMvc.perform(get("/api/v1/mortgages?borrowerId=BOR-001&" + query))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void malformedJsonIs400WithEnvelope() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages").contentType(MediaType.APPLICATION_JSON).content("{not json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.correlationId").exists());
    }

    @Test
    void sqlInjectionInPathIsPassedThroughAsAPlainValue() throws Exception {
        String probe = "MTG-1001' OR '1'='1";
        when(mortgageService.getMortgageById(probe)).thenThrow(ResourceNotFoundException.mortgage(probe));
        // The repository binds the value as a parameter, so the probe is just an unknown ID: 404, no 500, no data.
        mockMvc.perform(get("/api/v1/mortgages/{id}", probe))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("MORTGAGE_NOT_FOUND"));
        verify(mortgageService).getMortgageById(probe);
    }
}
