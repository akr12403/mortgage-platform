package com.capstone.mortgage.service;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.entity.ServicingHistory;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import com.capstone.mortgage.repository.ServicingHistoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Service
public class PaymentService {

    private final PaymentRepository paymentRepository;
    private final MortgageRepository mortgageRepository;
    private final ServicingHistoryRepository servicingHistoryRepository;

    public PaymentService(PaymentRepository paymentRepository,
                          MortgageRepository mortgageRepository,
                          ServicingHistoryRepository servicingHistoryRepository) {
        this.paymentRepository = paymentRepository;
        this.mortgageRepository = mortgageRepository;
        this.servicingHistoryRepository = servicingHistoryRepository;
    }

    @Transactional
    public Payment processPayment(Long mortgageId, Payment payment) {
        // 1. Find mortgage
        Mortgage mortgage = mortgageRepository.findById(mortgageId)
                .orElseThrow(() -> new RuntimeException("Mortgage not found with id: " + mortgageId));

        // 2. Associate payment and save
        payment.setMortgage(mortgage);
        Payment savedPayment = paymentRepository.save(payment);

        // 3. Update mortgage outstanding balance
        // 3. Update mortgage outstanding balance (fall back to loanAmount if balance is null)
        BigDecimal currentBalance = mortgage.getOutstandingBalance() != null
                ? mortgage.getOutstandingBalance()
                : mortgage.getLoanAmount();

        if (currentBalance != null) {
            mortgage.setOutstandingBalance(currentBalance.subtract(payment.getAmount()));
            mortgageRepository.save(mortgage);
        }

        // 4. Insert servicing history event PAYMENT_POSTED
        ServicingHistory history = new ServicingHistory();
        history.setMortgageId(mortgageId);
        history.setEventType("PAYMENT_POSTED");
        history.setDescription("Payment of " + payment.getAmount() + " posted successfully.");
        history.setCreatedAt(LocalDateTime.now());
        servicingHistoryRepository.save(history);

        return savedPayment;
    }
}