package com.capstone.mortgage.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import com.nimbusds.jose.jwk.source.ImmutableSecret;

import javax.crypto.SecretKey;
import java.time.Clock;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtKeysTest {

    private final JwtProperties properties =
            new JwtProperties("unit-test-secret-0123456789-abcdefghijklmnop", "capstone-mortgage-auth", 3600, 30);

    @Test
    void shortOrMissingSecret_FailsFast() {
        assertThatThrownBy(() -> JwtKeys.signingKey(new JwtProperties("too-short", "iss", 3600, 30)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("256 bits");
        assertThatThrownBy(() -> JwtKeys.signingKey(new JwtProperties(null, "iss", 3600, 30)))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void issuedTokenCarriesRequiredClaims() {
        SecretKey key = JwtKeys.signingKey(properties);
        TokenService tokenService = new TokenService(new NimbusJwtEncoder(new ImmutableSecret<>(key)), properties, Clock.systemUTC());
        JwtDecoder decoder = JwtKeys.decoder(key, properties);

        Jwt jwt = decoder.decode(tokenService.issue("risk@capstone.local", List.of("RISK_ANALYST")).accessToken());

        assertThat(jwt.getSubject()).isEqualTo("risk@capstone.local");
        assertThat(jwt.getClaimAsStringList("roles")).containsExactly("RISK_ANALYST");
        assertThat(jwt.getClaimAsString("iss")).isEqualTo("capstone-mortgage-auth");
        assertThat(jwt.getExpiresAt()).isAfter(jwt.getIssuedAt());
        assertThat(jwt.getId()).isNotBlank();
    }
}
