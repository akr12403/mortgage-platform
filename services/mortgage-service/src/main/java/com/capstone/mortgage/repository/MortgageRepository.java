package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Mortgage;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.EntityGraph;

@Repository
public interface MortgageRepository extends JpaRepository<Mortgage, UUID> {

    @EntityGraph(attributePaths = {"borrower", "loan"})
    Optional<Mortgage> findByMortgageExternalId(String mortgageExternalId);

    Page<Mortgage> findByBorrower_BorrowerExternalId(String borrowerExternalId, Pageable pageable);
}