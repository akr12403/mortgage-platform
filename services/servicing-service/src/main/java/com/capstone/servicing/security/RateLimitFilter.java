package com.capstone.servicing.security;

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

/** Per-user limit on state-changing requests (M6 Task 6.3). Runs after JWT authentication. */
public class RateLimitFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RateLimitFilter.class);
    private static final Set<String> WRITE_METHODS = Set.of("POST", "PUT", "PATCH", "DELETE");

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
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (properties.enabled() && WRITE_METHODS.contains(request.getMethod())
                && auth != null && auth.isAuthenticated() && !"anonymousUser".equals(auth.getName())) {
            RateLimiter.Decision decision = rateLimiter.tryAcquire(
                    "write-user:" + auth.getName(), properties.writesPerUserPerMinute(), Duration.ofMinutes(1));
            if (!decision.allowed()) {
                log.warn("Rate limit exceeded: {} {} by {}", request.getMethod(), request.getRequestURI(), auth.getName());
                errorWriter.writeRateLimited(response, decision.retryAfterSeconds());
                return;
            }
        }
        chain.doFilter(request, response);
    }
}
