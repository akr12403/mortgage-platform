package com.capstone.servicing.dto;

public class ErrorResponse {
    private String code;
    private String message;
    private String correlationId;

    public ErrorResponse(String code, String message, String correlationId) {
        this.code = code;
        this.message = message;
        this.correlationId = correlationId;
    }

    // Getters and Setters
    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
}