package com.capstone.mortgage.exception;

import org.springframework.http.HttpStatus;

/**
 * Domain rule violation mapped to a 4xx response in the shared error envelope.
 */
public class BusinessRuleException extends RuntimeException {

    private final String code;
    private final HttpStatus status;

    public BusinessRuleException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public static BusinessRuleException conflict(String code, String message) {
        return new BusinessRuleException(HttpStatus.CONFLICT, code, message);
    }

    public static BusinessRuleException badRequest(String code, String message) {
        return new BusinessRuleException(HttpStatus.BAD_REQUEST, code, message);
    }

    public String getCode() {
        return code;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
