package com.capstone.mortgage.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.time.LocalDate;

public record MortgageCreateRequest(
        @NotBlank String mortgageExternalId,
        @NotBlank String borrowerExternalId,
        @NotNull @DecimalMin("0.01") BigDecimal originalAmount,
        @NotNull @DecimalMin("0.00") BigDecimal outstandingBalance,
        @NotNull LocalDate originationDate,
        @Valid LoanTerms loan
) {
    public record LoanTerms(
            @NotBlank String loanExternalId,
            @NotNull @DecimalMin("0.0001") BigDecimal interestRate,
            @NotNull @jakarta.validation.constraints.Positive Integer termMonths,
            @NotBlank String underwritingDecision
    ) {}
}
