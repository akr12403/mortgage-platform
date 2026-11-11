package com.capstone.mortgage.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Duration;
import java.util.Set;

/**
 * Rate limits (M6 Task 6.3), applied inside the security chain right after JWT authentication:
 * - POST /api/v1/auth/login: per client IP (password spraying). Per-username limits are applied in AuthController.
 * - state-changing requests on /api/v1/**: per authenticated user (abuse of payment / origination endpoints).
 * The client IP is request.getRemoteAddr(); X-Forwarded-For is NOT trusted (spoofable) until a trusted proxy is
 * configured in M9.
 */
public class RateLimitFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RateLimitFilter.class);
    private static final Duration MINUTE = Duration.ofMinutes(1);
    private static final Set<String> WRITE_METHODS = Set.of("POST", "PUT", "PATCH", "DELETE");
    static final String LOGIN_PATH = "/api/v1/auth/login";

    private final RateLimiter rateLimiter;
    private final RateLimitProperties properties;
    private final SecurityErrorWriter errorWriter;

    public RateLimitFilter(RateLimiter rateLimiter, RateLimitProperties properties, SecurityErrorWriter errorWriter) {
        this.rateLimiter = rateLimiter;
        this.properties = properties;
        this.errorWriter = errorWriter;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        if (!properties.enabled()) {
            chain.doFilter(request, response);
            return;
        }
        String path = request.getRequestURI().substring(request.getContextPath().length());
        RateLimiter.Decision decision = null;

        if ("POST".equals(request.getMethod()) && LOGIN_PATH.equals(path)) {
            decision = rateLimiter.tryAcquire("login-ip:" + request.getRemoteAddr(), properties.loginPerIpPerMinute(), MINUTE);
        } else if (WRITE_METHODS.contains(request.getMethod()) && path.startsWith("/api/v1/")) {
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            if (auth != null && auth.isAuthenticated() && !"anonymousUser".equals(auth.getName())) {
                decision = rateLimiter.tryAcquire("write-user:" + auth.getName(), properties.writesPerUserPerMinute(), MINUTE);
            }
        }

        if (decision != null && !decision.allowed()) {
            log.warn("Rate limit exceeded: {} {} from {}", request.getMethod(), path, request.getRemoteAddr());
            errorWriter.writeRateLimited(response, decision.retryAfterSeconds());
            return;
        }
        chain.doFilter(request, response);
    }
}
