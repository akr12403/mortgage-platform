package com.capstone.mortgage.security;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * app.security.jwt.* — the secret comes from the JWT_SECRET env var (never committed) and must be
 * at least 256 bits (32 bytes) for HS256. Startup fails fast otherwise.
 */
@ConfigurationProperties(prefix = "app.security.jwt")
public record JwtProperties(
        String secret,
        @DefaultValue("capstone-mortgage-auth") String issuer,
        @DefaultValue("3600") long ttlSeconds,
        @DefaultValue("30") long clockSkewSeconds
) {
    public static final int MIN_SECRET_BYTES = 32;
}
