package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Mortgage;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface MortgageRepository extends JpaRepository<Mortgage, UUID> {

    @EntityGraph(attributePaths = {"borrower", "loan"})
    Optional<Mortgage> findByMortgageExternalId(String mortgageExternalId);

    boolean existsByMortgageExternalId(String mortgageExternalId);

    @EntityGraph(attributePaths = {"borrower", "loan"})
    Page<Mortgage> findByBorrower_BorrowerExternalId(String borrowerExternalId, Pageable pageable);
}
