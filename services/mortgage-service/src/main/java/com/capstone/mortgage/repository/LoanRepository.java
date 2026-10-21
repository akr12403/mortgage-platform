package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Loan;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface LoanRepository extends JpaRepository<Loan, UUID> {
    boolean existsByLoanExternalId(String loanExternalId);
}
