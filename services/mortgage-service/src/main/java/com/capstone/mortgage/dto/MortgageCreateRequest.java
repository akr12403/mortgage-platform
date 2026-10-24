package com.capstone.mortgage.dto;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;
import java.time.LocalDate;

public record MortgageCreateRequest(
        @NotBlank @Pattern(regexp = "MTG-\\d{4}", message = "must match MTG-{4 digits}") String mortgageExternalId,
        @NotBlank @Pattern(regexp = "BOR-\\d{3}", message = "must match BOR-{3 digits}") String borrowerExternalId,
        @NotNull @DecimalMin("0.01") @DecimalMax("100000000.00") @Digits(integer = 13, fraction = 2) BigDecimal originalAmount,
        @NotNull @DecimalMin("0.00") @DecimalMax("100000000.00") @Digits(integer = 13, fraction = 2) BigDecimal outstandingBalance,
        @NotNull @PastOrPresent LocalDate originationDate,
        @Valid LoanTerms loan
) {
    /** Cross-field rule: the outstanding balance can never exceed the original principal. */
    @JsonIgnore
    @AssertTrue(message = "outstandingBalance must not exceed originalAmount")
    public boolean isBalanceWithinOriginalAmount() {
        return originalAmount == null || outstandingBalance == null || outstandingBalance.compareTo(originalAmount) <= 0;
    }

    public record LoanTerms(
            @NotBlank @Pattern(regexp = "LOAN-\\d{4}", message = "must match LOAN-{4 digits}") String loanExternalId,
            @NotNull @DecimalMin("0.0001") @DecimalMax("0.5000") @Digits(integer = 2, fraction = 4) BigDecimal interestRate,
            @NotNull @Positive @Max(480) Integer termMonths,
            @NotBlank @Pattern(regexp = "PENDING|APPROVED|DECLINED", message = "must be PENDING, APPROVED or DECLINED")
            String underwritingDecision
    ) {}
}
