package com.capstone.mortgage.dto;

import java.time.Instant;

public class ErrorResponse {
    private String code;
    private String message;
    private String correlationId;
    private Instant timestamp;

    public ErrorResponse(String code, String message, String correlationId) {
        this.code = code;
        this.message = message;
        this.correlationId = correlationId;
        this.timestamp = Instant.now();
    }

    // Getters and Setters
    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }

    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }
}