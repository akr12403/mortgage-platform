package com.capstone.servicing.security;

import com.capstone.servicing.dto.ErrorResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;

import java.io.IOException;

/**
 * Writes 401/403 in the shared error envelope (guides/standards.md) instead of Spring's default HTML/blank body.
 * Never echoes the token or credentials back.
 */
public class SecurityErrorWriter implements AuthenticationEntryPoint, AccessDeniedHandler {

    private final ObjectMapper objectMapper;

    public SecurityErrorWriter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response, AuthenticationException ex)
            throws IOException {
        boolean badToken = ex instanceof InvalidTokenException;
        response.setHeader("WWW-Authenticate", badToken
                ? "Bearer error=\"invalid_token\", error_description=\"The access token is invalid or expired\""
                : "Bearer");
        write(response, HttpServletResponse.SC_UNAUTHORIZED,
                badToken ? "INVALID_TOKEN" : "UNAUTHORIZED",
                badToken ? "Access token is invalid or expired" : "Authentication is required");
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response, AccessDeniedException ex)
            throws IOException {
        write(response, HttpServletResponse.SC_FORBIDDEN, "ACCESS_DENIED", "You do not have permission to perform this action");
    }

    private void write(HttpServletResponse response, int status, String code, String message) throws IOException {
        String correlationId = MDC.get("correlationId");
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getOutputStream(),
                new ErrorResponse(code, message, correlationId != null ? correlationId : "UNKNOWN"));
    }
}
