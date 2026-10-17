package com.capstone.mortgage.service;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.entity.ServicingHistory;
import com.capstone.mortgage.events.EventPayloads;
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
    private final EventPublisherService eventPublisher; // Added event publisher

    public MortgageService(MortgageRepository mortgageRepository,
                           PaymentRepository paymentRepository,
                           ServicingHistoryRepository historyRepository,
                           EventPublisherService eventPublisher) {
        this.mortgageRepository = mortgageRepository;
        this.paymentRepository = paymentRepository;
        this.historyRepository = historyRepository;
        this.eventPublisher = eventPublisher;
    }

    public Mortgage getMortgageById(Long id) {
        return mortgageRepository.findById(id)
                .orElseThrow(() -> new jakarta.persistence.EntityNotFoundException("Mortgage not found with id: " + id));
    }

    @Transactional
    public Mortgage saveMortgage(Mortgage mortgage) {
        Mortgage saved = mortgageRepository.save(mortgage);

        // Publish MortgageCreated event via SNS
        var payload = new EventPayloads.MortgageCreatedPayload(
                "MTG-" + saved.getId(),
                saved.getBorrower() != null ? "BOR-" + saved.getBorrower().getId() : "BOR-UNKNOWN",
                saved.getLoanAmount(),
                "PENDING"
        );
        eventPublisher.publishEvent("MortgageCreated", payload);

        return saved;
    }

    public Page<Mortgage> getMortgagesByBorrower(Long borrowerId, Pageable pageable) {
        return mortgageRepository.findByBorrowerId(borrowerId, pageable);
    }

    @Transactional
    public Payment processPayment(Long mortgageId, Payment payment) {
        Mortgage mortgage = getMortgageById(mortgageId);

        payment.setMortgage(mortgage);
        Payment savedPayment = paymentRepository.save(payment);

        // Update outstanding balance transactionally if needed
        BigDecimal currentBalance = mortgage.getOutstandingBalance() != null
                ? mortgage.getOutstandingBalance()
                : mortgage.getLoanAmount();

        if (currentBalance != null) {
            mortgage.setOutstandingBalance(currentBalance.subtract(payment.getAmount()));
            mortgageRepository.save(mortgage);
        }

        // Insert servicing history event
        ServicingHistory history = new ServicingHistory(
                mortgageId,
                "PAYMENT_POSTED",
                "Payment posted successfully for amount: " + payment.getAmount()
        );
        historyRepository.save(history);

        // Publish PaymentReceived event via SNS
        var payload = new EventPayloads.PaymentReceivedPayload(
                "MTG-" + mortgage.getId(),
                payment.getAmount(),
                payment.getPaidDate(),
                mortgage.getOutstandingBalance()
        );
        eventPublisher.publishEvent("PaymentReceived", payload);

        return savedPayment;
    }

    public List<Payment> getPaymentsByMortgage(Long mortgageId) {
        return paymentRepository.findByMortgageId(mortgageId);
    }
}