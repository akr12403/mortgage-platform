package com.capstone.mortgage.security;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

/** Builds the HS256 signing key and a decoder that verifies signature, exp/nbf (with skew) and iss. */
public final class JwtKeys {

    private JwtKeys() {}

    public static SecretKey signingKey(JwtProperties properties) {
        String secret = properties.secret();
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < JwtProperties.MIN_SECRET_BYTES) {
            throw new IllegalStateException("JWT_SECRET must be set and at least " + JwtProperties.MIN_SECRET_BYTES
                    + " bytes (256 bits). Generate one with: openssl rand -base64 48");
        }
        return new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }

    public static JwtDecoder decoder(SecretKey key, JwtProperties properties) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build();
        OAuth2TokenValidator<Jwt> validator = new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ofSeconds(properties.clockSkewSeconds())),
                // exp is mandatory: tokens without an expiry are rejected
                new JwtClaimValidator<Instant>("exp", Objects::nonNull),
                new JwtIssuerValidator(properties.issuer()));
        decoder.setJwtValidator(validator);
        return decoder;
    }
}
