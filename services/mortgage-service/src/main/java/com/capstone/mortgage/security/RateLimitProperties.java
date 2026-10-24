package com.capstone.mortgage.security;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** app.security.rate-limit.* — per-minute budgets (M6 Task 6.3). */
@ConfigurationProperties(prefix = "app.security.rate-limit")
public record RateLimitProperties(
        @DefaultValue("true") boolean enabled,
        /* Login attempts per username per client IP (brute force / credential stuffing on one account). */
        @DefaultValue("10") int loginPerUserPerMinute,
        /* All login attempts from one client IP (password spraying across accounts). */
        @DefaultValue("60") int loginPerIpPerMinute,
        /* State-changing requests (POST/PUT/PATCH/DELETE) per authenticated user. */
        @DefaultValue("60") int writesPerUserPerMinute
) {}
