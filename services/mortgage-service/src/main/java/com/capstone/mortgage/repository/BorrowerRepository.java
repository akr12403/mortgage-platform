package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Borrower;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface BorrowerRepository extends JpaRepository<Borrower, Long> {
    Optional<Borrower> findByBorrowerExternalId(String borrowerExternalId);
}