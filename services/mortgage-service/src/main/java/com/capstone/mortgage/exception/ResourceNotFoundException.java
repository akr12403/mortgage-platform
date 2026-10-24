package com.capstone.mortgage.exception;

import jakarta.persistence.EntityNotFoundException;

/**
 * 404 with a specific error code from the standards (e.g. MORTGAGE_NOT_FOUND).
 * Extends EntityNotFoundException so existing handlers/tests keep working.
 */
public class ResourceNotFoundException extends EntityNotFoundException {

    private final String code;

    public ResourceNotFoundException(String code, String message) {
        super(message);
        this.code = code;
    }

    public static ResourceNotFoundException mortgage(String mortgageExternalId) {
        return new ResourceNotFoundException("MORTGAGE_NOT_FOUND", "Mortgage " + mortgageExternalId + " was not found");
    }

    public static ResourceNotFoundException borrower(String borrowerExternalId) {
        return new ResourceNotFoundException("BORROWER_NOT_FOUND", "Borrower " + borrowerExternalId + " was not found");
    }

    public String getCode() {
        return code;
    }
}
