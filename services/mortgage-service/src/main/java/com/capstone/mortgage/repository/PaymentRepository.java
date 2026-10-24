package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Payment;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

@Repository
public interface PaymentRepository extends JpaRepository<Payment, UUID> {

    List<Payment> findByMortgage_MortgageExternalIdOrderByDueDateAsc(String mortgageExternalId);

    boolean existsByMortgage_IdAndDueDateAndStatus(UUID mortgageId, LocalDate dueDate, String status);

    /**
     * Unpaid installments on ACTIVE mortgages that are due on or before the cutoff and have
     * no POSTED payment for the same due date. Used by the delinquency batch scan.
     */
    @Query("""
            select p from Payment p join fetch p.mortgage m
            where m.status = 'ACTIVE'
              and p.status in ('SCHEDULED', 'FAILED', 'REVERSED')
              and p.dueDate <= :cutoff
              and not exists (
                  select p2.id from Payment p2
                  where p2.mortgage = m and p2.dueDate = p.dueDate and p2.status = 'POSTED')
            order by p.dueDate asc
            """)
    List<Payment> findOverdueUnpaidOnActiveMortgages(@Param("cutoff") LocalDate cutoff);
}
