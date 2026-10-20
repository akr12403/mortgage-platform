package com.capstone.mortgage.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "loan")
public class Loan {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "loan_external_id", unique = true, nullable = false)
    private String loanExternalId;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "mortgage_id", nullable = false, unique = true)
    private Mortgage mortgage;

    @Column(name = "interest_rate", nullable = false, precision = 6, scale = 4)
    private BigDecimal interestRate;

    @Column(name = "term_months", nullable = false)
    private Integer termMonths;

    @Column(name = "underwriting_decision", nullable = false)
    private String underwritingDecision;

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }

    public String getLoanExternalId() { return loanExternalId; }
    public void setLoanExternalId(String loanExternalId) { this.loanExternalId = loanExternalId; }

    public Mortgage getMortgage() { return mortgage; }
    public void setMortgage(Mortgage mortgage) { this.mortgage = mortgage; }

    public BigDecimal getInterestRate() { return interestRate; }
    public void setInterestRate(BigDecimal interestRate) { this.interestRate = interestRate; }

    public Integer getTermMonths() { return termMonths; }
    public void setTermMonths(Integer termMonths) { this.termMonths = termMonths; }

    public String getUnderwritingDecision() { return underwritingDecision; }
    public void setUnderwritingDecision(String underwritingDecision) { this.underwritingDecision = underwritingDecision; }
}
