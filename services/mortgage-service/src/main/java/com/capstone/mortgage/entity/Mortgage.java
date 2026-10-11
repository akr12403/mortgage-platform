package com.capstone.mortgage.entity;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "mortgages")
public class Mortgage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "loan_amount", nullable = false, precision = 12, scale = 2)
    private BigDecimal loanAmount;

    @Column(name = "interest_rate", nullable = false, precision = 5, scale = 4)
    private BigDecimal interestRate;

    @Column(name = "term_years", nullable = false)
    private Integer termYears;

    @Column(name = "property_address", nullable = false)
    private String propertyAddress;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "borrower_id", nullable = false)
    private Borrower borrower;

    // Default constructor
    public Mortgage() {}

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public BigDecimal getLoanAmount() { return loanAmount; }
    public void setLoanAmount(BigDecimal loanAmount) { this.loanAmount = loanAmount; }

    public BigDecimal getInterestRate() { return interestRate; }
    public void setInterestRate(BigDecimal interestRate) { this.interestRate = interestRate; }

    public Integer getTermYears() { return termYears; }
    public void setTermYears(Integer termYears) { this.termYears = termYears; }

    public String getPropertyAddress() { return propertyAddress; }
    public void setPropertyAddress(String propertyAddress) { this.propertyAddress = propertyAddress; }

    public Borrower getBorrower() { return borrower; }
    public void setBorrower(Borrower borrower) { this.borrower = borrower; }
}