package com.capstone.mortgage.events;

import java.math.BigDecimal;
import java.time.LocalDate;

public class EventPayloads {
    public record MortgageCreatedPayload(
            String mortgageExternalId,
            String borrowerExternalId,
            BigDecimal originalAmount,
            String status
    ) {}

    public record PaymentReceivedPayload(
            String mortgageExternalId,
            BigDecimal paymentAmount,
            LocalDate paidDate,
            BigDecimal outstandingBalanceAfter
    ) {}

    public record PaymentMissedPayload(
            String mortgageExternalId,
            LocalDate dueDate,
            long daysPastDue
    ) {}

    public record LoanApprovedPayload(
            String mortgageExternalId,
            String loanExternalId,
            String underwritingDecision,
            String approvedByRole
    ) {}

    public record LoanDelinquentPayload(
            String mortgageExternalId,
            String delinquentSince,
            long daysPastDue,
            String severity
    ) {}
}