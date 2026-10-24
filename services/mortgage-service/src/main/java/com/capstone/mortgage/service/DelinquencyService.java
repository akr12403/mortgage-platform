package com.capstone.mortgage.service;

import com.capstone.mortgage.dto.DelinquencyScanResponse;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * Canonical delinquency rule (guides/standards.md):
 * a mortgage becomes DELINQUENT when no successful (POSTED) payment exists for a due date
 * 30+ calendar days after that due date.
 *
 * - PaymentMissed fires when a past-due installment is missed (failed/reversed attempt, or batch scan).
 * - LoanDelinquent fires when the DELINQUENT status is assigned.
 *
 * mortgage-service owns mortgage.status; the delinquency snapshot table is projected by
 * servicing-service from the LoanDelinquent event (see service-ownership-matrix.md).
 */
@Service
public class DelinquencyService {

    private static final Logger log = LoggerFactory.getLogger(DelinquencyService.class);
    public static final int DELINQUENCY_THRESHOLD_DAYS = 30;

    private final MortgageRepository mortgageRepository;
    private final PaymentRepository paymentRepository;
    private final EventPublisherService eventPublisher;
    private final Clock clock;

    public DelinquencyService(MortgageRepository mortgageRepository,
                              PaymentRepository paymentRepository,
                              EventPublisherService eventPublisher,
                              Clock clock) {
        this.mortgageRepository = mortgageRepository;
        this.paymentRepository = paymentRepository;
        this.eventPublisher = eventPublisher;
        this.clock = clock;
    }

    /** Called from a FAILED/REVERSED payment attempt whose due date has passed. */
    @Transactional
    public Optional<DelinquencyScanResponse.Transition> onMissedPayment(Mortgage mortgage, LocalDate dueDate) {
        LocalDate today = LocalDate.now(clock);
        if (dueDate == null || dueDate.isAfter(today)) {
            return Optional.empty();
        }
        if (paymentRepository.existsByMortgage_IdAndDueDateAndStatus(mortgage.getId(), dueDate, "POSTED")) {
            return Optional.empty();
        }
        long daysPastDue = ChronoUnit.DAYS.between(dueDate, today);
        eventPublisher.publishEvent("PaymentMissed", new EventPayloads.PaymentMissedPayload(
                mortgage.getMortgageExternalId(), dueDate, daysPastDue));
        return markDelinquentIfThresholdReached(mortgage, dueDate, daysPastDue);
    }

    /** Batch evaluation: run daily by DelinquencyScheduler and on demand via POST /api/v1/delinquency-evaluations for demos. */
    @Transactional
    public DelinquencyScanResponse evaluatePortfolio() {
        LocalDate today = LocalDate.now(clock);
        LocalDate cutoff = today.minusDays(DELINQUENCY_THRESHOLD_DAYS);

        // Oldest unpaid due date per ACTIVE mortgage (query is ordered by due date ascending).
        Map<UUID, Payment> oldestUnpaid = new LinkedHashMap<>();
        for (Payment payment : paymentRepository.findOverdueUnpaidOnActiveMortgages(cutoff)) {
            oldestUnpaid.putIfAbsent(payment.getMortgage().getId(), payment);
        }

        List<DelinquencyScanResponse.Transition> transitions = new ArrayList<>();
        for (Payment payment : oldestUnpaid.values()) {
            Mortgage mortgage = payment.getMortgage();
            long daysPastDue = ChronoUnit.DAYS.between(payment.getDueDate(), today);
            eventPublisher.publishEvent("PaymentMissed", new EventPayloads.PaymentMissedPayload(
                    mortgage.getMortgageExternalId(), payment.getDueDate(), daysPastDue));
            markDelinquentIfThresholdReached(mortgage, payment.getDueDate(), daysPastDue)
                    .ifPresent(transitions::add);
        }
        log.info("Delinquency evaluation complete: {} candidate(s), {} transitioned", oldestUnpaid.size(), transitions.size());
        return new DelinquencyScanResponse(Instant.now(clock), transitions.size(), transitions);
    }

    static String severityFor(long daysPastDue) {
        if (daysPastDue >= 90) {
            return "CRITICAL";
        }
        if (daysPastDue >= 60) {
            return "SEVERE";
        }
        return "MODERATE";
    }

    private Optional<DelinquencyScanResponse.Transition> markDelinquentIfThresholdReached(
            Mortgage mortgage, LocalDate dueDate, long daysPastDue) {
        if (daysPastDue < DELINQUENCY_THRESHOLD_DAYS || !"ACTIVE".equals(mortgage.getStatus())) {
            return Optional.empty();
        }
        String delinquentSince = dueDate.plusDays(DELINQUENCY_THRESHOLD_DAYS).toString();
        String severity = severityFor(daysPastDue);

        mortgage.setStatus("DELINQUENT");
        mortgageRepository.save(mortgage);
        eventPublisher.publishEvent("LoanDelinquent", new EventPayloads.LoanDelinquentPayload(
                mortgage.getMortgageExternalId(), delinquentSince, daysPastDue, severity));
        log.info("Mortgage {} transitioned to DELINQUENT ({} days past due, {})",
                mortgage.getMortgageExternalId(), daysPastDue, severity);
        return Optional.of(new DelinquencyScanResponse.Transition(
                mortgage.getMortgageExternalId(), delinquentSince, daysPastDue, severity));
    }
}
