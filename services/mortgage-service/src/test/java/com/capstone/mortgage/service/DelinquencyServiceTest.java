package com.capstone.mortgage.service;

import com.capstone.mortgage.dto.DelinquencyScanResponse;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class DelinquencyServiceTest {

    // "Today" for every test: 2026-03-15
    private final Clock clock = Clock.fixed(Instant.parse("2026-03-15T12:00:00Z"), ZoneOffset.UTC);
    private final MortgageRepository mortgageRepository = mock(MortgageRepository.class);
    private final PaymentRepository paymentRepository = mock(PaymentRepository.class);
    private final EventPublisherService publisher = mock(EventPublisherService.class);
    private final DelinquencyService service =
            new DelinquencyService(mortgageRepository, paymentRepository, publisher, clock);

    private static Mortgage activeMortgage(String externalId) {
        Mortgage mortgage = new Mortgage();
        mortgage.setId(UUID.randomUUID());
        mortgage.setMortgageExternalId(externalId);
        mortgage.setStatus("ACTIVE");
        return mortgage;
    }

    @Test
    void missedPayment45DaysPastDue_marksDelinquentAndPublishesBothEvents() {
        Mortgage mortgage = activeMortgage("MTG-1002");
        LocalDate dueDate = LocalDate.parse("2026-01-29"); // 45 days before 2026-03-15

        Optional<DelinquencyScanResponse.Transition> result = service.onMissedPayment(mortgage, dueDate);

        assertThat(result).isPresent();
        assertThat(result.get().daysPastDue()).isEqualTo(45);
        assertThat(result.get().severity()).isEqualTo("MODERATE");
        assertThat(result.get().delinquentSince()).isEqualTo("2026-02-28");
        assertThat(mortgage.getStatus()).isEqualTo("DELINQUENT");
        verify(publisher).publishEvent(eq("PaymentMissed"), any(EventPayloads.PaymentMissedPayload.class));

        ArgumentCaptor<EventPayloads.LoanDelinquentPayload> captor =
                ArgumentCaptor.forClass(EventPayloads.LoanDelinquentPayload.class);
        verify(publisher).publishEvent(eq("LoanDelinquent"), captor.capture());
        assertThat(captor.getValue().mortgageExternalId()).isEqualTo("MTG-1002");
        assertThat(captor.getValue().daysPastDue()).isEqualTo(45);
    }

    @Test
    void missedPaymentUnder30Days_onlyPublishesPaymentMissed() {
        Mortgage mortgage = activeMortgage("MTG-1001");

        Optional<DelinquencyScanResponse.Transition> result =
                service.onMissedPayment(mortgage, LocalDate.parse("2026-03-05"));

        assertThat(result).isEmpty();
        assertThat(mortgage.getStatus()).isEqualTo("ACTIVE");
        verify(publisher).publishEvent(eq("PaymentMissed"), any(EventPayloads.PaymentMissedPayload.class));
        verify(publisher, never()).publishEvent(eq("LoanDelinquent"), any());
    }

    @Test
    void installmentAlreadyPaid_publishesNothing() {
        Mortgage mortgage = activeMortgage("MTG-1001");
        LocalDate dueDate = LocalDate.parse("2026-01-01");
        when(paymentRepository.existsByMortgage_IdAndDueDateAndStatus(mortgage.getId(), dueDate, "POSTED")).thenReturn(true);

        assertThat(service.onMissedPayment(mortgage, dueDate)).isEmpty();
        verifyNoInteractions(publisher);
    }

    @Test
    void futureDueDate_isNotAMissedPayment() {
        assertThat(service.onMissedPayment(activeMortgage("MTG-1001"), LocalDate.parse("2026-04-01"))).isEmpty();
        verifyNoInteractions(publisher);
    }

    @Test
    void alreadyDelinquentMortgage_doesNotRepublishLoanDelinquent() {
        Mortgage mortgage = activeMortgage("MTG-1002");
        mortgage.setStatus("DELINQUENT");

        service.onMissedPayment(mortgage, LocalDate.parse("2026-01-01"));

        verify(publisher).publishEvent(eq("PaymentMissed"), any(EventPayloads.PaymentMissedPayload.class));
        verify(publisher, never()).publishEvent(eq("LoanDelinquent"), any());
    }

    @Test
    void batchScan_transitionsEachMortgageOnceUsingOldestUnpaidInstallment() {
        Mortgage mortgage = activeMortgage("MTG-1004");
        Payment older = new Payment();
        older.setMortgage(mortgage);
        older.setDueDate(LocalDate.parse("2025-12-01"));
        Payment newer = new Payment();
        newer.setMortgage(mortgage);
        newer.setDueDate(LocalDate.parse("2026-01-01"));
        when(paymentRepository.findOverdueUnpaidOnActiveMortgages(LocalDate.parse("2026-02-13")))
                .thenReturn(List.of(older, newer));

        DelinquencyScanResponse response = service.evaluatePortfolio();

        assertThat(response.mortgagesTransitioned()).isEqualTo(1);
        assertThat(response.transitions().get(0).daysPastDue()).isEqualTo(104);
        assertThat(response.transitions().get(0).severity()).isEqualTo("CRITICAL");
        verify(publisher, times(1)).publishEvent(eq("LoanDelinquent"), any());
    }

    @Test
    void severityBands() {
        assertThat(DelinquencyService.severityFor(30)).isEqualTo("MODERATE");
        assertThat(DelinquencyService.severityFor(59)).isEqualTo("MODERATE");
        assertThat(DelinquencyService.severityFor(60)).isEqualTo("SEVERE");
        assertThat(DelinquencyService.severityFor(90)).isEqualTo("CRITICAL");
    }
}
