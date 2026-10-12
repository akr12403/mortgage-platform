package com.capstone.mortgage.service;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.entity.ServicingHistory;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import com.capstone.mortgage.repository.ServicingHistoryRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class MortgageService {

    private final MortgageRepository mortgageRepository;
    private final PaymentRepository paymentRepository;
    private final ServicingHistoryRepository historyRepository;

    public MortgageService(MortgageRepository mortgageRepository,
                           PaymentRepository paymentRepository,
                           ServicingHistoryRepository historyRepository) {
        this.mortgageRepository = mortgageRepository;
        this.paymentRepository = paymentRepository;
        this.historyRepository = historyRepository;
    }

    public Mortgage getMortgageById(Long id) {
        return mortgageRepository.findById(id)
                .orElseThrow(() -> new jakarta.persistence.EntityNotFoundException("Mortgage not found with id: " + id));
    }

    public Mortgage saveMortgage(Mortgage mortgage) {
        return mortgageRepository.save(mortgage);
    }

    public Page<Mortgage> getMortgagesByBorrower(Long borrowerId, Pageable pageable) {
        return mortgageRepository.findByBorrowerId(borrowerId, pageable);
    }

    @Transactional
    public Payment processPayment(Long mortgageId, Payment payment) {
        Mortgage mortgage = getMortgageById(mortgageId);

        payment.setMortgage(mortgage);
        Payment savedPayment = paymentRepository.save(payment);

        // Update outstanding balance transactionally (assuming a balance field exists or adjusting principal)
        // If your Mortgage entity tracks balance, update it here.

        // Insert servicing history event
        ServicingHistory history = new ServicingHistory(
                mortgageId,
                "PAYMENT_POSTED",
                "Payment posted successfully for amount: " + payment.getAmount()
        );
        historyRepository.save(history);

        return savedPayment;
    }

    public List<Payment> getPaymentsByMortgage(Long mortgageId) {
        return paymentRepository.findByMortgageId(mortgageId);
    }
}