package com.capstone.mortgage.security;

import com.capstone.mortgage.controller.MortgageController;
import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * End-to-end filter behavior with REAL signed tokens (Task 6.1 step 3):
 * valid → 200, missing → 401 UNAUTHORIZED, tampered / expired / wrong issuer / wrong key → 401 INVALID_TOKEN.
 */
@WebMvcTest(MortgageController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
class JwtAuthenticationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtEncoder jwtEncoder;

    @Autowired
    private JwtProperties jwtProperties;

    @MockBean
    private MortgageService mortgageService;

    @MockBean
    private PaymentService paymentService;

    @BeforeEach
    void stubMortgage() {
        Mortgage mortgage = new Mortgage();
        mortgage.setMortgageExternalId("MTG-1001");
        mortgage.setStatus("ACTIVE");
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId("BOR-001");
        mortgage.setBorrower(borrower);
        when(mortgageService.getMortgageById("MTG-1001")).thenReturn(mortgage);
    }

    private String token(JwtEncoder encoder, JwtProperties properties, Clock clock) {
        return new TokenService(encoder, properties, clock)
                .issue("servicing@capstone.local", List.of("SERVICING_AGENT")).accessToken();
    }

    private String validToken() {
        return token(jwtEncoder, jwtProperties, Clock.systemUTC());
    }

    @Test
    void validToken_Returns200() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001").header("Authorization", "Bearer " + validToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mortgageExternalId").value("MTG-1001"));
    }

    @Test
    void missingToken_Returns401Envelope() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001").header("X-Correlation-Id", "7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate", "Bearer"))
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.correlationId").value("7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .andExpect(jsonPath("$.timestamp").exists());
    }

    @Test
    void missingToken_OnMutation_Returns401() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void tamperedToken_Returns401InvalidToken() throws Exception {
        String[] parts = validToken().split("\\.");
        // Swap the payload for one claiming ADMIN; the signature no longer matches.
        String forgedPayload = java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(
                "{\"sub\":\"attacker\",\"roles\":[\"ADMIN\"],\"iss\":\"capstone-mortgage-auth\",\"exp\":4102444800}"
                        .getBytes(StandardCharsets.UTF_8));
        String tampered = parts[0] + "." + forgedPayload + "." + parts[2];

        mockMvc.perform(get("/api/v1/mortgages/MTG-1001").header("Authorization", "Bearer " + tampered))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_TOKEN"));
    }

    @Test
    void expiredToken_Returns401InvalidToken() throws Exception {
        Clock twoHoursAgo = Clock.fixed(Instant.now().minus(Duration.ofHours(2)), ZoneOffset.UTC);
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001")
                        .header("Authorization", "Bearer " + token(jwtEncoder, jwtProperties, twoHoursAgo)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_TOKEN"));
    }

    @Test
    void wrongIssuer_Returns401InvalidToken() throws Exception {
        JwtProperties otherIssuer = new JwtProperties(jwtProperties.secret(), "some-other-issuer", 900, 30);
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001")
                        .header("Authorization", "Bearer " + token(jwtEncoder, otherIssuer, Clock.systemUTC())))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_TOKEN"));
    }

    @Test
    void tokenSignedWithDifferentKey_Returns401InvalidToken() throws Exception {
        JwtEncoder attackerEncoder = new NimbusJwtEncoder(new ImmutableSecret<>(new SecretKeySpec(
                "attacker-controlled-secret-0123456789-xyz".getBytes(StandardCharsets.UTF_8), "HmacSHA256")));
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001")
                        .header("Authorization", "Bearer " + token(attackerEncoder, jwtProperties, Clock.systemUTC())))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_TOKEN"));
    }

    @Test
    void garbageToken_Returns401InvalidToken() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001").header("Authorization", "Bearer not-a-jwt"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_TOKEN"));
    }

    @Test
    void securityHeadersPresent() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001").header("Authorization", "Bearer " + validToken()))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(header().string("X-Frame-Options", "DENY"));
    }
}
