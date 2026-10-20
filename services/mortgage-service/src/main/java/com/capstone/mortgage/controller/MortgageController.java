package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.dto.MortgageCreateRequest;
import com.capstone.mortgage.dto.MortgageResponse;
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
    public ResponseEntity<Page<Mortgage>> getMortgagesByBorrower(
            @RequestParam String borrowerId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        Page<Mortgage> mortgages = mortgageService.getMortgagesByBorrower(borrowerId, PageRequest.of(page, size));
        return ResponseEntity.ok(mortgages);
    }

    @GetMapping("/{id}/payments")
    public ResponseEntity<List<Payment>> getPayments(@PathVariable String id) {
        List<Payment> payments = mortgageService.getPaymentsByMortgage(id);
        return ResponseEntity.ok(payments);
    }

    @PostMapping("/{id}/payments")
    public ResponseEntity<Payment> createPayment(
            @PathVariable String id,
            @Valid @RequestBody Payment payment,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationId) {

        // Log or use correlationId if needed for tracing
        Payment savedPayment = paymentService.processPayment(id, payment);
        return ResponseEntity.ok(savedPayment);
    }
}