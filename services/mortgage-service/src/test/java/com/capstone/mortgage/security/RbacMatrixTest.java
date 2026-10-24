package com.capstone.mortgage.security;

import com.capstone.mortgage.controller.BorrowerController;
import com.capstone.mortgage.controller.DelinquencyController;
import com.capstone.mortgage.controller.MortgageController;
import com.capstone.mortgage.dto.DelinquencyScanResponse;
import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.repository.BorrowerRepository;
import com.capstone.mortgage.service.DelinquencyService;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Stream;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * M6 Task 6.2: every mortgage-service endpoint x all five roles. Allowed → 2xx, wrong role → 403 ACCESS_DENIED.
 * Mirrors the matrix in docs/security/security-controls.md; update both together.
 */
@WebMvcTest(controllers = {MortgageController.class, BorrowerController.class, DelinquencyController.class})
@ActiveProfiles("test")
@Import(SecurityConfig.class)
class RbacMatrixTest {

    private static final String MORTGAGE_BODY = """
            {"mortgageExternalId":"MTG-1010","borrowerExternalId":"BOR-001","originalAmount":320000.00,
             "outstandingBalance":318500.00,"originationDate":"2025-06-01"}""";
    private static final String BORROWER_BODY = """
            {"borrowerExternalId":"BOR-010","firstName":"Alex","lastName":"Rivera","email":"alex.rivera@example.test"}""";
    private static final String PAYMENT_BODY = """
            {"dueDate":"2026-03-01","paidDate":"2026-03-02","amount":1850.00,"status":"POSTED"}""";
    private static final String DECISION_BODY = "{\"decision\":\"APPROVED\"}";

    record Endpoint(String name, HttpMethod method, String path, String body, Set<String> allowed) {
        @Override
        public String toString() {
            return name;
        }
    }

    static final List<Endpoint> ENDPOINTS = List.of(
            new Endpoint("POST /borrowers", HttpMethod.POST, "/api/v1/borrowers", BORROWER_BODY, Set.of(Rbac.ORIGINATION)),
            new Endpoint("GET /borrowers/{id}", HttpMethod.GET, "/api/v1/borrowers/BOR-001", null, Set.of(Rbac.BORROWER_PII_READ)),
            new Endpoint("POST /mortgages", HttpMethod.POST, "/api/v1/mortgages", MORTGAGE_BODY, Set.of(Rbac.ORIGINATION)),
            new Endpoint("GET /mortgages/{id}", HttpMethod.GET, "/api/v1/mortgages/MTG-1001", null, Set.of(Rbac.ALL_ROLES)),
            new Endpoint("GET /mortgages?borrowerId", HttpMethod.GET, "/api/v1/mortgages?borrowerId=BOR-001", null, Set.of(Rbac.ALL_ROLES)),
            new Endpoint("POST underwriting-decision", HttpMethod.POST, "/api/v1/mortgages/MTG-1001/underwriting-decision", DECISION_BODY, Set.of(Rbac.ORIGINATION)),
            new Endpoint("GET payments", HttpMethod.GET, "/api/v1/mortgages/MTG-1001/payments", null, Set.of(Rbac.ALL_ROLES)),
            new Endpoint("POST payments", HttpMethod.POST, "/api/v1/mortgages/MTG-1001/payments", PAYMENT_BODY, Set.of(Rbac.SERVICING_WRITE)),
            new Endpoint("POST delinquency-evaluations", HttpMethod.POST, "/api/v1/delinquency-evaluations", null, Set.of(Rbac.SERVICING_WRITE))
    );

    static Stream<Arguments> endpointRoleMatrix() {
        List<Arguments> cases = new ArrayList<>();
        for (Endpoint endpoint : ENDPOINTS) {
            for (String role : Rbac.ALL_ROLES) {
                cases.add(Arguments.of(endpoint, role, endpoint.allowed().contains(role)));
            }
        }
        return cases.stream();
    }

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MortgageService mortgageService;
    @MockBean
    private PaymentService paymentService;
    @MockBean
    private DelinquencyService delinquencyService;
    @MockBean
    private BorrowerRepository borrowerRepository;

    @BeforeEach
    void stubHappyPaths() {
        Borrower borrower = new Borrower();
        borrower.setId(UUID.randomUUID());
        borrower.setBorrowerExternalId("BOR-001");
        Mortgage mortgage = new Mortgage();
        mortgage.setMortgageExternalId("MTG-1001");
        mortgage.setStatus("ACTIVE");
        mortgage.setBorrower(borrower);
        Payment payment = new Payment();
        payment.setAmount(new BigDecimal("1850.00"));
        payment.setDueDate(LocalDate.parse("2026-03-01"));
        payment.setStatus("POSTED");

        when(borrowerRepository.findByBorrowerExternalId("BOR-001")).thenReturn(Optional.of(borrower));
        when(borrowerRepository.findByBorrowerExternalId("BOR-010")).thenReturn(Optional.empty());
        when(borrowerRepository.save(any(Borrower.class))).thenReturn(borrower);
        when(mortgageService.saveMortgage(any(MortgageCreateRequest.class), anyString())).thenReturn(mortgage);
        when(mortgageService.getMortgageById("MTG-1001")).thenReturn(mortgage);
        when(mortgageService.getMortgagesByBorrower(anyString(), any())).thenReturn(Page.empty());
        when(mortgageService.recordUnderwritingDecision(anyString(), anyString(), anyString())).thenReturn(mortgage);
        when(mortgageService.getPaymentsByMortgage("MTG-1001")).thenReturn(List.of());
        when(paymentService.processPayment(anyString(), any(Payment.class), any()))
                .thenReturn(new PaymentService.PaymentOutcome(payment, false));
        when(delinquencyService.evaluatePortfolio()).thenReturn(new DelinquencyScanResponse(Instant.now(), 0, List.of()));
    }

    private MockHttpServletRequestBuilder build(Endpoint endpoint) {
        MockHttpServletRequestBuilder builder = request(endpoint.method(), endpoint.path());
        if (endpoint.body() != null) {
            builder.contentType(MediaType.APPLICATION_JSON).content(endpoint.body());
        }
        return builder;
    }

    @ParameterizedTest(name = "{0} as {1} -> allowed={2}")
    @MethodSource("endpointRoleMatrix")
    void roleMatrix(Endpoint endpoint, String role, boolean allowed) throws Exception {
        var result = mockMvc.perform(build(endpoint).with(user(role.toLowerCase() + "@capstone.local").roles(role)));
        if (allowed) {
            result.andExpect(status().is2xxSuccessful());
        } else {
            result.andExpect(status().isForbidden())
                    .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
                    .andExpect(jsonPath("$.correlationId").exists());
        }
    }

    @Test
    void supportCannotApproveLoan_M10Journey4() throws Exception {
        mockMvc.perform(build(ENDPOINTS.get(5)).with(user("support@capstone.local").roles(Rbac.SUPPORT)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void wrongRoleIsRejectedBeforeValidation() throws Exception {
        // An invalid body from a forbidden role must still get 403 (not 400): authorization runs first.
        mockMvc.perform(request(HttpMethod.POST, "/api/v1/mortgages").contentType(MediaType.APPLICATION_JSON).content("{}")
                        .with(user("support@capstone.local").roles(Rbac.SUPPORT)))
                .andExpect(status().isForbidden());
    }

    @Test
    void tokenWithNoKnownRole_IsDeniedEverywhere() throws Exception {
        for (Endpoint endpoint : ENDPOINTS) {
            mockMvc.perform(build(endpoint).with(user("nobody@capstone.local").roles("GUEST")))
                    .andExpect(status().isForbidden());
        }
    }

    @Test
    void unmappedRouteIsDeniedByDefault() throws Exception {
        mockMvc.perform(request(HttpMethod.DELETE, "/api/v1/mortgages/MTG-1001").with(user("admin@capstone.local").roles(Rbac.ADMIN)))
                .andExpect(status().isForbidden());
    }

    @Test
    void matrixCoversEveryRoleGroupMember() {
        // Guard against typos in Rbac groups (every member must be a real role code).
        Set<String> all = Set.of(Rbac.ALL_ROLES);
        for (String[] group : List.of(Rbac.ORIGINATION, Rbac.SERVICING_WRITE, Rbac.BORROWER_PII_READ)) {
            org.assertj.core.api.Assertions.assertThat(all).containsAll(Arrays.asList(group));
        }
    }
}
