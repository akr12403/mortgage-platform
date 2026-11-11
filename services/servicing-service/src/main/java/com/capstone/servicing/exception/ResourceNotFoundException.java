package com.capstone.servicing.exception;

import jakarta.persistence.EntityNotFoundException;

public class ResourceNotFoundException extends EntityNotFoundException {

    private final String code;

    public ResourceNotFoundException(String code, String message) {
        super(message);
        this.code = code;
    }

    public static ResourceNotFoundException mortgage(String mortgageExternalId) {
        return new ResourceNotFoundException("MORTGAGE_NOT_FOUND", "Mortgage " + mortgageExternalId + " was not found");
    }

    public String getCode() {
        return code;
    }
}
