package com.capstone.mortgage.entity;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import com.fasterxml.jackson.annotation.JsonManagedReference;

@Entity
@Table(name = "mortgage")
public class Mortgage {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "mortgage_external_id", unique = true, nullable = false)
    private String mortgageExternalId;

    @Column(nullable = false)
    private String status;

    @Column(name = "original_amount", nullable = false, precision = 15, scale = 2)
    private BigDecimal originalAmount;

    @Column(name = "outstanding_balance", nullable = false, precision = 15, scale = 2)
    private BigDecimal outstandingBalance;

    @Column(name = "origination_date", nullable = false)
    private java.time.LocalDate originationDate;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "borrower_id", nullable = false)
    @com.fasterxml.jackson.annotation.JsonBackReference
    private Borrower borrower;

    @OneToMany(mappedBy = "mortgage", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    @JsonManagedReference
    private List<Payment> payments;

    @OneToOne(mappedBy = "mortgage", fetch = FetchType.LAZY)
    private Loan loan;

    // Default constructor
    public Mortgage() {}

    // Getters and Setters
    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }

    public String getMortgageExternalId() { return mortgageExternalId; }
    public void setMortgageExternalId(String mortgageExternalId) { this.mortgageExternalId = mortgageExternalId; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public BigDecimal getOutstandingBalance() { return outstandingBalance; }
    public void setOutstandingBalance(BigDecimal outstandingBalance) { this.outstandingBalance = outstandingBalance; }

    public BigDecimal getOriginalAmount() { return originalAmount; }
    public void setOriginalAmount(BigDecimal originalAmount) { this.originalAmount = originalAmount; }

    public java.time.LocalDate getOriginationDate() { return originationDate; }
    public void setOriginationDate(java.time.LocalDate originationDate) { this.originationDate = originationDate; }

    public Borrower getBorrower() { return borrower; }
    public void setBorrower(Borrower borrower) { this.borrower = borrower; }

    public List<Payment> getPayments() { return payments; }
    public void setPayments(List<Payment> payments) { this.payments = payments; }

    public Loan getLoan() { return loan; }
    public void setLoan(Loan loan) { this.loan = loan; }
}