package com.capstone.mortgage.service;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Loan;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.repository.BorrowerRepository;
import com.capstone.mortgage.repository.LoanRepository;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;


@Service
public class MortgageService {

    private final MortgageRepository mortgageRepository;
    private final BorrowerRepository borrowerRepository;
    private final LoanRepository loanRepository;
    private final PaymentRepository paymentRepository;
    private final EventPublisherService eventPublisher; // Added event publisher

    public MortgageService(MortgageRepository mortgageRepository,
                           BorrowerRepository borrowerRepository,
                           LoanRepository loanRepository,
                           PaymentRepository paymentRepository,
                           EventPublisherService eventPublisher) {
        this.mortgageRepository = mortgageRepository;
        this.borrowerRepository = borrowerRepository;
        this.loanRepository = loanRepository;
        this.paymentRepository = paymentRepository;
        this.eventPublisher = eventPublisher;
    }

    public Mortgage getMortgageById(String mortgageExternalId) {
        return mortgageRepository.findByMortgageExternalId(mortgageExternalId)
                .orElseThrow(() -> new jakarta.persistence.EntityNotFoundException("Mortgage " + mortgageExternalId + " was not found"));
    }

    @Transactional
    public Mortgage saveMortgage(MortgageCreateRequest request) {
        var borrower = borrowerRepository.findByBorrowerExternalId(request.borrowerExternalId())
                .orElseThrow(() -> new jakarta.persistence.EntityNotFoundException(
                        "Borrower " + request.borrowerExternalId() + " was not found"));
        Mortgage mortgage = new Mortgage();
        mortgage.setMortgageExternalId(request.mortgageExternalId());
        mortgage.setStatus("PENDING");
        mortgage.setOriginalAmount(request.originalAmount());
        mortgage.setOutstandingBalance(request.outstandingBalance());
        mortgage.setOriginationDate(request.originationDate());
        mortgage.setBorrower(borrower);
        Mortgage saved = mortgageRepository.save(mortgage);

        if (request.loan() != null) {
            Loan loan = new Loan();
            loan.setLoanExternalId(request.loan().loanExternalId());
            loan.setMortgage(saved);
            loan.setInterestRate(request.loan().interestRate());
            loan.setTermMonths(request.loan().termMonths());
            loan.setUnderwritingDecision(request.loan().underwritingDecision());
            Loan savedLoan = loanRepository.save(loan);
            mortgage.setLoan(savedLoan);
            if ("APPROVED".equals(savedLoan.getUnderwritingDecision())) {
                eventPublisher.publishEvent("LoanApproved", new EventPayloads.LoanApprovedPayload(
                        saved.getMortgageExternalId(), savedLoan.getLoanExternalId(),
                        savedLoan.getUnderwritingDecision(), "UNDERWRITER"
                ));
            }
        }

        var payload = new EventPayloads.MortgageCreatedPayload(
                saved.getMortgageExternalId(),
                saved.getBorrower().getBorrowerExternalId(),
                saved.getOriginalAmount(),
                saved.getStatus()
        );
        eventPublisher.publishEvent("MortgageCreated", payload);

        return saved;
    }

    public Page<Mortgage> getMortgagesByBorrower(String borrowerExternalId, Pageable pageable) {
        return mortgageRepository.findByBorrower_BorrowerExternalId(borrowerExternalId, pageable);
    }

    public List<Payment> getPaymentsByMortgage(String mortgageExternalId) {
        return paymentRepository.findByMortgage_MortgageExternalIdOrderByDueDateAsc(mortgageExternalId);
    }

}