package com.capstone.servicing.security;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * app.security.jwt.* — must use the SAME JWT_SECRET and issuer as mortgage-service (the token issuer).
 * servicing-service only validates tokens; it never issues them.
 */
@ConfigurationProperties(prefix = "app.security.jwt")
public record JwtProperties(
        String secret,
        @DefaultValue("capstone-mortgage-auth") String issuer,
        @DefaultValue("30") long clockSkewSeconds
) {
    public static final int MIN_SECRET_BYTES = 32;
}
