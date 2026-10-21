package com.capstone.mortgage.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * Daily batch that applies the 30-day delinquency rule (PaymentMissed "batch" path in standards.md).
 * Kept separate from DelinquencyService so the call goes through the transactional proxy.
 */
@Component
public class DelinquencyScheduler {

    private static final Logger log = LoggerFactory.getLogger(DelinquencyScheduler.class);

    private final DelinquencyService delinquencyService;

    public DelinquencyScheduler(DelinquencyService delinquencyService) {
        this.delinquencyService = delinquencyService;
    }

    @Scheduled(cron = "${app.delinquency.scan-cron:0 0 2 * * *}", zone = "UTC")
    public void runDailyEvaluation() {
        MDC.put(EventPublisherService.MDC_CORRELATION_ID_KEY, UUID.randomUUID().toString());
        try {
            delinquencyService.evaluatePortfolio();
        } catch (RuntimeException e) {
            log.error("Scheduled delinquency evaluation failed", e);
        } finally {
            MDC.remove(EventPublisherService.MDC_CORRELATION_ID_KEY);
        }
    }
}
