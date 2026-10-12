package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Mortgage;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface MortgageRepository extends JpaRepository<Mortgage, Long> {
    Page<Mortgage> findByBorrowerId(Long borrowerId, Pageable pageable);
}