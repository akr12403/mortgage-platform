package com.capstone.mortgage.service;

import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.entity.Loan;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.repository.BorrowerRepository;
import com.capstone.mortgage.repository.LoanRepository;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class MortgageServiceTest {

    private final MortgageRepository mortgageRepository = mock(MortgageRepository.class);
    private final BorrowerRepository borrowerRepository = mock(BorrowerRepository.class);
    private final LoanRepository loanRepository = mock(LoanRepository.class);
    private final PaymentRepository paymentRepository = mock(PaymentRepository.class);
    private final EventPublisherService publisher = mock(EventPublisherService.class);
    private final MortgageService service = new MortgageService(
            mortgageRepository, borrowerRepository, loanRepository, paymentRepository, publisher);

    @BeforeEach
    void setUp() {
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId("BOR-001");
        when(borrowerRepository.findByBorrowerExternalId("BOR-001")).thenReturn(Optional.of(borrower));
        when(mortgageRepository.save(any(Mortgage.class))).thenAnswer(invocation -> {
            Mortgage m = invocation.getArgument(0);
            if (m.getId() == null) {
                m.setId(UUID.randomUUID());
            }
            return m;
        });
        when(loanRepository.save(any(Loan.class))).thenAnswer(invocation -> invocation.getArgument(0));
    }

    private static MortgageCreateRequest request(String decision) {
        return new MortgageCreateRequest("MTG-1010", "BOR-001", new BigDecimal("320000.00"),
                new BigDecimal("318500.00"), LocalDate.parse("2025-06-01"),
                new MortgageCreateRequest.LoanTerms("LOAN-2010", new BigDecimal("0.0650"), 360, decision));
    }

    @Test
    void createWithApprovedLoan_publishesMortgageCreatedThenLoanApproved_andActivates() {
        Mortgage saved = service.saveMortgage(request("APPROVED"));

        assertThat(saved.getStatus()).isEqualTo("ACTIVE");
        assertThat(saved.getLoan().getUnderwritingDecision()).isEqualTo("APPROVED");

        ArgumentCaptor<EventPayloads.MortgageCreatedPayload> created =
                ArgumentCaptor.forClass(EventPayloads.MortgageCreatedPayload.class);
        InOrder order = inOrder(publisher);
        order.verify(publisher).publishEvent(eq("MortgageCreated"), created.capture());
        order.verify(publisher).publishEvent(eq("LoanApproved"), any(EventPayloads.LoanApprovedPayload.class));
        assertThat(created.getValue().status()).isEqualTo("PENDING");
        assertThat(created.getValue().borrowerExternalId()).isEqualTo("BOR-001");
    }

    @Test
    void createWithPendingLoan_staysPendingAndOnlyPublishesMortgageCreated() {
        Mortgage saved = service.saveMortgage(request("PENDING"));

        assertThat(saved.getStatus()).isEqualTo("PENDING");
        verify(publisher).publishEvent(eq("MortgageCreated"), any());
        verify(publisher, never()).publishEvent(eq("LoanApproved"), any());
    }

    @Test
    void duplicateMortgageId_isRejectedWith409() {
        when(mortgageRepository.existsByMortgageExternalId("MTG-1010")).thenReturn(true);

        assertThatThrownBy(() -> service.saveMortgage(request("APPROVED")))
                .isInstanceOf(BusinessRuleException.class)
                .hasMessageContaining("already exists");
        verifyNoInteractions(publisher);
    }

    @Test
    void approvalWorkflow_approvesPendingLoan() {
        Mortgage mortgage = service.saveMortgage(request("PENDING"));
        when(mortgageRepository.findByMortgageExternalId("MTG-1010")).thenReturn(Optional.of(mortgage));
        clearInvocations(publisher);

        Mortgage approved = service.recordUnderwritingDecision("MTG-1010", "APPROVED", "UNDERWRITER");

        assertThat(approved.getStatus()).isEqualTo("ACTIVE");
        ArgumentCaptor<EventPayloads.LoanApprovedPayload> captor =
                ArgumentCaptor.forClass(EventPayloads.LoanApprovedPayload.class);
        verify(publisher).publishEvent(eq("LoanApproved"), captor.capture());
        assertThat(captor.getValue().loanExternalId()).isEqualTo("LOAN-2010");
        assertThat(captor.getValue().approvedByRole()).isEqualTo("UNDERWRITER");
    }

    @Test
    void approvalWorkflow_rejectsSecondDecision() {
        Mortgage mortgage = service.saveMortgage(request("APPROVED"));
        when(mortgageRepository.findByMortgageExternalId("MTG-1010")).thenReturn(Optional.of(mortgage));

        assertThatThrownBy(() -> service.recordUnderwritingDecision("MTG-1010", "DECLINED", "UNDERWRITER"))
                .isInstanceOf(BusinessRuleException.class)
                .hasMessageContaining("already APPROVED");
    }

    @Test
    void declinedLoan_closesPendingMortgageWithoutLoanApproved() {
        Mortgage mortgage = service.saveMortgage(request("PENDING"));
        when(mortgageRepository.findByMortgageExternalId("MTG-1010")).thenReturn(Optional.of(mortgage));

        Mortgage declined = service.recordUnderwritingDecision("MTG-1010", "DECLINED", "UNDERWRITER");

        assertThat(declined.getStatus()).isEqualTo("CLOSED");
        verify(publisher, never()).publishEvent(eq("LoanApproved"), any());
    }
}
