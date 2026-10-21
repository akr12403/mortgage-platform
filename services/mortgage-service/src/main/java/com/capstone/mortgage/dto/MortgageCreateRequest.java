package com.capstone.mortgage.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;
import java.time.LocalDate;

public record MortgageCreateRequest(
        @NotBlank @Pattern(regexp = "MTG-\\d{4}", message = "must match MTG-{4 digits}") String mortgageExternalId,
        @NotBlank @Pattern(regexp = "BOR-\\d{3}", message = "must match BOR-{3 digits}") String borrowerExternalId,
        @NotNull @DecimalMin("0.01") BigDecimal originalAmount,
        @NotNull @DecimalMin("0.00") BigDecimal outstandingBalance,
        @NotNull LocalDate originationDate,
        @Valid LoanTerms loan
) {
    public record LoanTerms(
            @NotBlank @Pattern(regexp = "LOAN-\\d{4}", message = "must match LOAN-{4 digits}") String loanExternalId,
            @NotNull @DecimalMin("0.0001") BigDecimal interestRate,
            @NotNull @Positive Integer termMonths,
            @NotBlank @Pattern(regexp = "PENDING|APPROVED|DECLINED", message = "must be PENDING, APPROVED or DECLINED")
            String underwritingDecision
    ) {}
}
