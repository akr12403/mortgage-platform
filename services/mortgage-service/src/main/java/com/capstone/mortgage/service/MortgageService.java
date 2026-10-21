package com.capstone.mortgage.service;

import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.entity.Loan;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.events.EventPayloads;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.exception.ResourceNotFoundException;
import com.capstone.mortgage.repository.BorrowerRepository;
import com.capstone.mortgage.repository.LoanRepository;
import com.capstone.mortgage.repository.MortgageRepository;
import com.capstone.mortgage.repository.PaymentRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Mortgage lifecycle: PENDING (created) -> ACTIVE (loan APPROVED) | CLOSED (loan DECLINED).
 * Publishes MortgageCreated and LoanApproved (after commit, via EventPublisherService).
 */
@Service
public class MortgageService {

    private final MortgageRepository mortgageRepository;
    private final BorrowerRepository borrowerRepository;
    private final LoanRepository loanRepository;
    private final PaymentRepository paymentRepository;
    private final EventPublisherService eventPublisher;

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

    @Transactional(readOnly = true)
    public Mortgage getMortgageById(String mortgageExternalId) {
        return mortgageRepository.findByMortgageExternalId(mortgageExternalId)
                .orElseThrow(() -> ResourceNotFoundException.mortgage(mortgageExternalId));
    }

    @Transactional
    public Mortgage saveMortgage(MortgageCreateRequest request) {
        if (mortgageRepository.existsByMortgageExternalId(request.mortgageExternalId())) {
            throw BusinessRuleException.conflict("MORTGAGE_ALREADY_EXISTS",
                    "Mortgage " + request.mortgageExternalId() + " already exists");
        }
        if (request.loan() != null && loanRepository.existsByLoanExternalId(request.loan().loanExternalId())) {
            throw BusinessRuleException.conflict("LOAN_ALREADY_EXISTS",
                    "Loan " + request.loan().loanExternalId() + " already exists");
        }
        var borrower = borrowerRepository.findByBorrowerExternalId(request.borrowerExternalId())
                .orElseThrow(() -> ResourceNotFoundException.borrower(request.borrowerExternalId()));

        Mortgage mortgage = new Mortgage();
        mortgage.setMortgageExternalId(request.mortgageExternalId());
        mortgage.setStatus("PENDING");
        mortgage.setOriginalAmount(request.originalAmount());
        mortgage.setOutstandingBalance(request.outstandingBalance());
        mortgage.setOriginationDate(request.originationDate());
        mortgage.setBorrower(borrower);
        Mortgage saved = mortgageRepository.save(mortgage);

        // MortgageCreated always describes the mortgage as created (PENDING).
        eventPublisher.publishEvent("MortgageCreated", new EventPayloads.MortgageCreatedPayload(
                saved.getMortgageExternalId(),
                borrower.getBorrowerExternalId(),
                saved.getOriginalAmount(),
                saved.getStatus()
        ));

        if (request.loan() != null) {
            Loan loan = new Loan();
            loan.setLoanExternalId(request.loan().loanExternalId());
            loan.setMortgage(saved);
            loan.setInterestRate(request.loan().interestRate());
            loan.setTermMonths(request.loan().termMonths());
            loan.setUnderwritingDecision("PENDING");
            Loan savedLoan = loanRepository.save(loan);
            saved.setLoan(savedLoan);

            // A decision supplied at creation goes through the same approval workflow stub.
            String requestedDecision = request.loan().underwritingDecision();
            if (!"PENDING".equals(requestedDecision)) {
                applyUnderwritingDecision(saved, savedLoan, requestedDecision, "UNDERWRITER");
            }
        }
        return saved;
    }

    /** Approval workflow stub: POST /api/v1/mortgages/{id}/underwriting-decision. */
    @Transactional
    public Mortgage recordUnderwritingDecision(String mortgageExternalId, String decision, String decidedByRole) {
        Mortgage mortgage = getMortgageById(mortgageExternalId);
        Loan loan = mortgage.getLoan();
        if (loan == null) {
            throw new ResourceNotFoundException("LOAN_NOT_FOUND", "Mortgage " + mortgageExternalId + " has no loan to underwrite");
        }
        if (!"PENDING".equals(loan.getUnderwritingDecision())) {
            throw BusinessRuleException.conflict("UNDERWRITING_ALREADY_DECIDED",
                    "Loan " + loan.getLoanExternalId() + " is already " + loan.getUnderwritingDecision());
        }
        applyUnderwritingDecision(mortgage, loan, decision, decidedByRole);
        return mortgage;
    }

    private void applyUnderwritingDecision(Mortgage mortgage, Loan loan, String decision, String decidedByRole) {
        loan.setUnderwritingDecision(decision);
        loanRepository.save(loan);

        if ("APPROVED".equals(decision)) {
            if ("PENDING".equals(mortgage.getStatus())) {
                mortgage.setStatus("ACTIVE");
                mortgageRepository.save(mortgage);
            }
            eventPublisher.publishEvent("LoanApproved", new EventPayloads.LoanApprovedPayload(
                    mortgage.getMortgageExternalId(), loan.getLoanExternalId(), decision, decidedByRole));
        } else if ("DECLINED".equals(decision) && "PENDING".equals(mortgage.getStatus())) {
            mortgage.setStatus("CLOSED");
            mortgageRepository.save(mortgage);
        }
    }

    @Transactional(readOnly = true)
    public Page<Mortgage> getMortgagesByBorrower(String borrowerExternalId, Pageable pageable) {
        return mortgageRepository.findByBorrower_BorrowerExternalId(borrowerExternalId, pageable);
    }

    @Transactional(readOnly = true)
    public List<Payment> getPaymentsByMortgage(String mortgageExternalId) {
        if (!mortgageRepository.existsByMortgageExternalId(mortgageExternalId)) {
            throw ResourceNotFoundException.mortgage(mortgageExternalId);
        }
        return paymentRepository.findByMortgage_MortgageExternalIdOrderByDueDateAsc(mortgageExternalId);
    }
}
