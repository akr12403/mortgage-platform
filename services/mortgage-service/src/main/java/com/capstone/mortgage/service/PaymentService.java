package com.capstone.mortgage.service;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.exception.ResourceNotFoundException;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Payment posting. POSTED reduces the balance and publishes PaymentReceived; a FAILED/REVERSED
 * attempt for a past due date publishes PaymentMissed and may trigger LoanDelinquent.
 * Optional Idempotency-Key header: same key + same body replays the original payment, same key +
 * different body returns 409.
 */
@Service
public class PaymentService {

    public record PaymentOutcome(Payment payment, boolean replayed) {}

    private final PaymentRepository paymentRepository;
    private final MortgageRepository mortgageRepository;
    private final EventPublisherService eventPublisher;
    private final DelinquencyService delinquencyService;
    private final JdbcTemplate jdbcTemplate;

    public PaymentService(PaymentRepository paymentRepository,
                          MortgageRepository mortgageRepository,
                          EventPublisherService eventPublisher,
                          DelinquencyService delinquencyService,
                          JdbcTemplate jdbcTemplate) {
        this.paymentRepository = paymentRepository;
        this.mortgageRepository = mortgageRepository;
        this.eventPublisher = eventPublisher;
        this.delinquencyService = delinquencyService;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public Payment processPayment(String mortgageExternalId, Payment payment) {
        return processPayment(mortgageExternalId, payment, null).payment();
    }

    @Transactional
    public PaymentOutcome processPayment(String mortgageExternalId, Payment payment, String idempotencyKey) {
        boolean idempotent = idempotencyKey != null && !idempotencyKey.isBlank();
        String fingerprint = fingerprint(mortgageExternalId, payment);

        if (idempotent) {
            List<Map<String, Object>> existing = jdbcTemplate.queryForList(
                    "SELECT request_fingerprint, payment_id FROM idempotency_record WHERE idempotency_key = ?",
                    idempotencyKey);
            if (!existing.isEmpty()) {
                if (!fingerprint.equals(existing.get(0).get("request_fingerprint"))) {
                    throw BusinessRuleException.conflict("IDEMPOTENCY_KEY_REUSED",
                            "Idempotency-Key " + idempotencyKey + " was already used with a different request");
                }
                UUID paymentId = (UUID) existing.get(0).get("payment_id");
                Payment original = paymentRepository.findById(paymentId)
                        .orElseThrow(() -> new IllegalStateException("Idempotency record points at missing payment " + paymentId));
                return new PaymentOutcome(original, true);
            }
        }

        Mortgage mortgage = mortgageRepository.findByMortgageExternalId(mortgageExternalId)
                .orElseThrow(() -> ResourceNotFoundException.mortgage(mortgageExternalId));

        if ("POSTED".equals(payment.getStatus()) && payment.getPaidDate() == null) {
            throw BusinessRuleException.badRequest("VALIDATION_ERROR", "paidDate: is required when status is POSTED");
        }

        payment.setMortgage(mortgage);
        // Flush so the payment row exists before the JDBC idempotency insert references it.
        Payment savedPayment = paymentRepository.saveAndFlush(payment);

        if ("POSTED".equals(payment.getStatus())) {
            BigDecimal newBalance = mortgage.getOutstandingBalance().subtract(payment.getAmount()).max(BigDecimal.ZERO);
            mortgage.setOutstandingBalance(newBalance);
            mortgageRepository.save(mortgage);
            eventPublisher.publishEvent("PaymentReceived", new EventPayloads.PaymentReceivedPayload(
                    mortgage.getMortgageExternalId(), payment.getAmount(), payment.getPaidDate(), newBalance));
        } else if ("FAILED".equals(payment.getStatus()) || "REVERSED".equals(payment.getStatus())) {
            delinquencyService.onMissedPayment(mortgage, payment.getDueDate());
        }

        if (idempotent) {
            jdbcTemplate.update(
                    "INSERT INTO idempotency_record (idempotency_key, request_fingerprint, payment_id) VALUES (?, ?, ?)",
                    idempotencyKey, fingerprint, savedPayment.getId());
        }
        return new PaymentOutcome(savedPayment, false);
    }

    private static String fingerprint(String mortgageExternalId, Payment payment) {
        return String.join("|",
                mortgageExternalId,
                Objects.toString(payment.getDueDate(), ""),
                Objects.toString(payment.getPaidDate(), ""),
                payment.getAmount() == null ? "" : payment.getAmount().stripTrailingZeros().toPlainString(),
                Objects.toString(payment.getStatus(), ""));
    }
}
