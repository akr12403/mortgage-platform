package com.capstone.mortgage.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import org.springframework.web.util.ServletRequestPathUtils;

import java.io.IOException;

/**
 * M9 Task 9.3: one structured "http_request" log line per request, for request rate, 5xx rate and latency in Splunk
 * (field contract: docs/operations/observability.md).
 *
 * <p>Runs just inside {@link CorrelationIdFilter}, so the correlationId is still in the MDC when the line is written.
 * Logs the route TEMPLATE (e.g. /api/v1/mortgages/{id}), never the raw path, query string, headers or body: no
 * mortgage numbers or tokens in the logs, and a bounded number of routes to group by. Requests rejected before
 * routing (security filter 401/403/429) are logged with the template they were aimed at; unknown paths with
 * route "unmatched".
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger ACCESS_LOG = LoggerFactory.getLogger("http.access");

    private final ObjectProvider<RequestMappingHandlerMapping> handlerMappings;

    public RequestLoggingFilter(
            @Qualifier("requestMappingHandlerMapping") ObjectProvider<RequestMappingHandlerMapping> handlerMappings) {
        this.handlerMappings = handlerMappings;
    }

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
            ACCESS_LOG.atInfo()
                    .addKeyValue("http.method", request.getMethod())
                    .addKeyValue("http.route", route(request))
                    .addKeyValue("http.status", status)
                    .addKeyValue("durationMs", Math.round((System.nanoTime() - started) / 100_000.0) / 10.0)
                    .log("http_request");
        }
    }

    /**
     * The route template the request matched. M9 RCA 2026-11-10 (B-25): requests rejected in the security filter
     * chain (401, 403, 429 rate limit) never reach the dispatcher, so no template is recorded; look up the template
     * they were aimed at, so throttled or rejected payments still show up under the payment route.
     */
    private String route(HttpServletRequest request) {
        Object matched = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        if (matched != null) {
            return matched.toString();
        }
        RequestMappingHandlerMapping mapping = handlerMappings.getIfAvailable();
        if (mapping != null) {
            try {
                if (!ServletRequestPathUtils.hasParsedRequestPath(request)) {
                    ServletRequestPathUtils.parseAndCache(request);
                }
                if (mapping.getHandler(request) != null) {
                    Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                    if (pattern != null) {
                        return pattern.toString();
                    }
                }
            } catch (Exception noRoute) {
                // unknown path or method not allowed: stays "unmatched"
            }
        }
        return "unmatched";
    }
}
