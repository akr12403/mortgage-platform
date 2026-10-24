package com.capstone.servicing.security;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** app.security.rate-limit.* (M6 Task 6.3). Login lives in mortgage-service; here only writes are limited. */
@ConfigurationProperties(prefix = "app.security.rate-limit")
public record RateLimitProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("60") int writesPerUserPerMinute
) {}
