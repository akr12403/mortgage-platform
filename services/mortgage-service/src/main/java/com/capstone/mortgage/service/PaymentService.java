package com.capstone.mortgage.service;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.entity.ServicingHistory;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import com.capstone.mortgage.repository.ServicingHistoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;

@Service
public class PaymentService {

    private final PaymentRepository paymentRepository;
    private final MortgageRepository mortgageRepository;
    private final ServicingHistoryRepository servicingHistoryRepository;
    private final EventPublisherService eventPublisher; // Added event publisher
    private final JdbcTemplate jdbcTemplate;

    public PaymentService(PaymentRepository paymentRepository,
                          MortgageRepository mortgageRepository,
                          ServicingHistoryRepository servicingHistoryRepository,
                          EventPublisherService eventPublisher,
                          JdbcTemplate jdbcTemplate) {
        this.paymentRepository = paymentRepository;
        this.mortgageRepository = mortgageRepository;
        this.servicingHistoryRepository = servicingHistoryRepository;
        this.eventPublisher = eventPublisher;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public Payment processPayment(String mortgageExternalId, Payment payment) {
        Mortgage mortgage = mortgageRepository.findByMortgageExternalId(mortgageExternalId)
                .orElseThrow(() -> new jakarta.persistence.EntityNotFoundException("Mortgage " + mortgageExternalId + " was not found"));

        // 2. Associate payment and save
        payment.setMortgage(mortgage);
        Payment savedPayment = paymentRepository.save(payment);

        // 3. Update mortgage outstanding balance (fall back to loanAmount if balance is null)
        BigDecimal currentBalance = mortgage.getOutstandingBalance() != null
            ? mortgage.getOutstandingBalance()
            : mortgage.getOriginalAmount();

        if ("POSTED".equals(payment.getStatus()) && currentBalance != null) {
            mortgage.setOutstandingBalance(currentBalance.subtract(payment.getAmount()));
            mortgageRepository.save(mortgage);
        }

        ServicingHistory history = new ServicingHistory();
        history.setMortgageId(mortgage.getId());
        if ("POSTED".equals(payment.getStatus())) {
            history.setEventType("PAYMENT_POSTED");
            history.setDescription("Payment posted for amount: " + payment.getAmount());
            servicingHistoryRepository.save(history);
            eventPublisher.publishEvent("PaymentReceived", new EventPayloads.PaymentReceivedPayload(
                mortgage.getMortgageExternalId(), payment.getAmount(), payment.getPaidDate(),
                mortgage.getOutstandingBalance()
            ));
        } else {
            history.setEventType("PAYMENT_" + payment.getStatus());
            history.setDescription("Payment " + payment.getStatus().toLowerCase() + " for amount: " + payment.getAmount());
            servicingHistoryRepository.save(history);
        }

        if (("FAILED".equals(payment.getStatus()) || "REVERSED".equals(payment.getStatus()))
            && payment.getDueDate() != null
            && !payment.getDueDate().isAfter(java.time.LocalDate.now())) {
            var missedPayload = new EventPayloads.PaymentMissedPayload(
                mortgage.getMortgageExternalId(), payment.getDueDate(),
                Math.max(0, java.time.temporal.ChronoUnit.DAYS.between(payment.getDueDate(), java.time.LocalDate.now()))
            );
            eventPublisher.publishEvent("PaymentMissed", missedPayload);

            long daysPastDue = java.time.temporal.ChronoUnit.DAYS.between(payment.getDueDate(), java.time.LocalDate.now());
            boolean successfulPaymentExists = Boolean.TRUE.equals(jdbcTemplate.queryForObject("""
                    SELECT EXISTS (
                        SELECT 1 FROM payment
                        WHERE mortgage_id = ? AND due_date = ? AND status = 'POSTED'
                    )
                    """, Boolean.class, mortgage.getId(), payment.getDueDate()));
            if (daysPastDue >= 30 && !successfulPaymentExists && !"DELINQUENT".equals(mortgage.getStatus())) {
                mortgage.setStatus("DELINQUENT");
                mortgageRepository.save(mortgage);
                jdbcTemplate.update("""
                        INSERT INTO delinquency (mortgage_id, delinquent_since, days_past_due, severity)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT (mortgage_id) DO UPDATE SET
                            days_past_due = EXCLUDED.days_past_due,
                            severity = EXCLUDED.severity
                        """, mortgage.getId(), payment.getDueDate(), daysPastDue,
                        daysPastDue >= 90 ? "CRITICAL" : daysPastDue >= 60 ? "SEVERE" : "MODERATE");
                eventPublisher.publishEvent("LoanDelinquent", new EventPayloads.LoanDelinquentPayload(
                        mortgage.getMortgageExternalId(), payment.getDueDate().toString(), daysPastDue,
                        daysPastDue >= 90 ? "CRITICAL" : daysPastDue >= 60 ? "SEVERE" : "MODERATE"
                ));
            }
        }

        return savedPayment;
    }
}