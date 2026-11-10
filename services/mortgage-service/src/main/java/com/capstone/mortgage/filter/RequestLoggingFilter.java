package com.capstone.mortgage.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

import java.io.IOException;

/**
 * M9 Task 9.3: one structured "http_request" log line per request, for request rate, 5xx rate and latency in Splunk
 * (field contract: docs/operations/observability.md).
 *
 * <p>Runs just inside {@link CorrelationIdFilter}, so the correlationId is still in the MDC when the line is written.
 * Logs the route TEMPLATE (e.g. /api/v1/mortgages/{id}), never the raw path, query string, headers or body: no
 * mortgage numbers or tokens in the logs, and a bounded number of routes to group by. Requests rejected before
 * routing (security filter 401/403, unknown paths) are logged with route "unmatched".
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger ACCESS_LOG = LoggerFactory.getLogger("http.access");

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getRequestURI().startsWith("/actuator/health"); // container health checks, not traffic
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long started = System.nanoTime();
        int status = 500; // if the chain throws, the container answers 500
        try {
            chain.doFilter(request, response);
            status = response.getStatus();
        } finally {
            Object route = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            ACCESS_LOG.atInfo()
                    .addKeyValue("http.method", request.getMethod())
                    .addKeyValue("http.route", route != null ? route.toString() : "unmatched")
                    .addKeyValue("http.status", status)
                    .addKeyValue("durationMs", Math.round((System.nanoTime() - started) / 100_000.0) / 10.0)
                    .log("http_request");
        }
    }
}
