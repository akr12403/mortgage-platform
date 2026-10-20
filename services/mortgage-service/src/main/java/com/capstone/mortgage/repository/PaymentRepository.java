package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.Payment;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;
import java.util.UUID;

@Repository
public interface PaymentRepository extends JpaRepository<Payment, UUID> {
    List<Payment> findByMortgage_MortgageExternalIdOrderByDueDateAsc(String mortgageExternalId);
}