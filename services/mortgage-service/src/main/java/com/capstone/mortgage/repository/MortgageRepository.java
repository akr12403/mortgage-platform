package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Mortgage;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

@Repository
public interface MortgageRepository extends JpaRepository<Mortgage, Long> {

    @Query(value = "SELECT m FROM Mortgage m LEFT JOIN FETCH m.payments WHERE m.borrower.id = :borrowerId",
            countQuery = "SELECT count(m) FROM Mortgage m WHERE m.borrower.id = :borrowerId")
    Page<Mortgage> findByBorrowerId(@Param("borrowerId") Long borrowerId, Pageable pageable);
}