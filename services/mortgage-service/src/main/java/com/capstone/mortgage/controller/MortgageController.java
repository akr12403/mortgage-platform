package com.capstone.mortgage.controller;

import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.dto.MortgageResponse;
import com.capstone.mortgage.dto.UnderwritingDecisionRequest;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.service.MortgageService;
import com.capstone.mortgage.service.PaymentService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/mortgages")
public class MortgageController {

    private final MortgageService mortgageService;
    private final PaymentService paymentService;

    public MortgageController(MortgageService mortgageService, PaymentService paymentService) {
        this.mortgageService = mortgageService;
        this.paymentService = paymentService;
    }

    @PostMapping
    public ResponseEntity<MortgageResponse> createMortgage(@Valid @RequestBody MortgageCreateRequest request) {
        Mortgage saved = mortgageService.saveMortgage(request);
        return new ResponseEntity<>(MortgageResponse.from(saved), HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<MortgageResponse> getMortgageById(@PathVariable String id) {
        return ResponseEntity.ok(MortgageResponse.from(mortgageService.getMortgageById(id)));
    }

    @GetMapping
    public ResponseEntity<Page<MortgageResponse>> getMortgagesByBorrower(
            @RequestParam String borrowerId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        Page<Mortgage> mortgages = mortgageService.getMortgagesByBorrower(borrowerId, PageRequest.of(page, size));
        return ResponseEntity.ok(mortgages.map(MortgageResponse::from));
    }

    /** Approval workflow stub (M5): records the underwriting decision and emits LoanApproved when approved. */
    @PostMapping("/{id}/underwriting-decision")
    public ResponseEntity<MortgageResponse> recordUnderwritingDecision(
            @PathVariable String id,
            @Valid @RequestBody UnderwritingDecisionRequest request) {
        Mortgage mortgage = mortgageService.recordUnderwritingDecision(id, request.decision(), request.roleOrDefault());
        return ResponseEntity.ok(MortgageResponse.from(mortgage));
    }

    @GetMapping("/{id}/payments")
    public ResponseEntity<List<Payment>> getPayments(@PathVariable String id) {
        return ResponseEntity.ok(mortgageService.getPaymentsByMortgage(id));
    }

    @PostMapping("/{id}/payments")
    public ResponseEntity<Payment> createPayment(
            @PathVariable String id,
            @Valid @RequestBody Payment payment,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        PaymentService.PaymentOutcome outcome = paymentService.processPayment(id, payment, idempotencyKey);
        return ResponseEntity.ok()
                .header("Idempotent-Replayed", Boolean.toString(outcome.replayed()))
                .body(outcome.payment());
    }
}
