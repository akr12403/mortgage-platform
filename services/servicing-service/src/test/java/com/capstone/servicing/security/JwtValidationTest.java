package com.capstone.servicing.security;

import com.capstone.servicing.controller.ServicingController;
import com.capstone.servicing.service.ServicingService;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Collections;
import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** servicing-service accepts tokens issued by mortgage-service (same secret + issuer) and rejects everything else. */
@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
class JwtValidationTest {

    private static final String TEST_SECRET = "test-only-jwt-secret-0123456789-abcdefghijklmnop";

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ServicingService servicingService;

    private static String token(String secret, String issuer, Instant expiresAt) {
        var encoder = new NimbusJwtEncoder(new ImmutableSecret<>(
                new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256")));
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject("servicing@capstone.local")
                .issuedAt(expiresAt.minusSeconds(3600))
                .expiresAt(expiresAt)
                .claim("roles", List.of("SERVICING_AGENT"))
                .build();
        return encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims)).getTokenValue();
    }

    @Test
    void tokenFromMortgageServiceIssuer_IsAccepted() throws Exception {
        when(servicingService.getServicingHistory("MTG-1001")).thenReturn(Collections.emptyList());
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history")
                        .header("Authorization", "Bearer " + token(TEST_SECRET, "capstone-mortgage-auth", Instant.now().plusSeconds(600))))
                .andExpect(status().isOk());
    }

    @Test
    void noToken_Returns401() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void noToken_OnMutation_Returns401() throws Exception {
        mockMvc.perform(post("/api/v1/mortgages/MTG-1001/servicing-events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventType\":\"ESCROW_ANALYSIS\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredToken_Returns401() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history")
                        .header("Authorization", "Bearer " + token(TEST_SECRET, "capstone-mortgage-auth", Instant.now().minusSeconds(600))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_TOKEN"));
    }

    @Test
    void wrongSecretOrIssuer_Returns401() throws Exception {
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history")
                        .header("Authorization", "Bearer " + token("some-other-secret-0123456789-abcdefghijk", "capstone-mortgage-auth", Instant.now().plusSeconds(600))))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/v1/mortgages/MTG-1001/servicing-history")
                        .header("Authorization", "Bearer " + token(TEST_SECRET, "evil-issuer", Instant.now().plusSeconds(600))))
                .andExpect(status().isUnauthorized());
    }
}
