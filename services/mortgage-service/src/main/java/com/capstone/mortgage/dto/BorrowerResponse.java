package com.capstone.mortgage.dto;

import com.capstone.mortgage.entity.Borrower;

import java.time.LocalDate;
import java.util.UUID;

/** Matches reference/sample-api-contracts.md; never serializes the JPA entity graph. */
public record BorrowerResponse(
        UUID id,
        String borrowerExternalId,
        String firstName,
        String lastName,
        String email,
        String phone,
        LocalDate dateOfBirth
) {
    public static BorrowerResponse from(Borrower borrower) {
        return new BorrowerResponse(borrower.getId(), borrower.getBorrowerExternalId(), borrower.getFirstName(),
                borrower.getLastName(), borrower.getEmail(), borrower.getPhone(), borrower.getDateOfBirth());
    }
}
