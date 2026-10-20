package com.capstone.mortgage.dto;

import com.capstone.mortgage.entity.Mortgage;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

public record MortgageResponse(
        UUID id,
        String mortgageExternalId,
        String borrowerExternalId,
        String status,
        BigDecimal originalAmount,
        BigDecimal outstandingBalance,
        LocalDate originationDate,
        LoanResponse loan
) {
    public static MortgageResponse from(Mortgage mortgage) {
        var loan = mortgage.getLoan();
        LoanResponse loanResponse = loan == null ? null : new LoanResponse(
                loan.getLoanExternalId(), loan.getInterestRate(), loan.getTermMonths(), loan.getUnderwritingDecision()
        );
        return new MortgageResponse(
                mortgage.getId(), mortgage.getMortgageExternalId(), mortgage.getBorrower().getBorrowerExternalId(),
                mortgage.getStatus(), mortgage.getOriginalAmount(), mortgage.getOutstandingBalance(),
                mortgage.getOriginationDate(), loanResponse
        );
    }

    public record LoanResponse(String loanExternalId, BigDecimal interestRate, Integer termMonths, String underwritingDecision) {}
}
