package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.entity.Payment;
import com.capstone.mortgage.service.MortgageService;
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

    public MortgageController(MortgageService mortgageService) {
        this.mortgageService = mortgageService;
    }

    @PostMapping
    public ResponseEntity<Mortgage> createMortgage(@Valid @RequestBody Mortgage mortgage) {
        Mortgage saved = mortgageService.saveMortgage(mortgage);
        return new ResponseEntity<>(saved, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Mortgage> getMortgageById(@PathVariable Long id) {
        return ResponseEntity.ok(mortgageService.getMortgageById(id));
    }

    @GetMapping
    public ResponseEntity<Page<Mortgage>> getMortgagesByBorrower(
            @RequestParam Long borrowerId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        Page<Mortgage> mortgages = mortgageService.getMortgagesByBorrower(borrowerId, PageRequest.of(page, size));
        return ResponseEntity.ok(mortgages);
    }

    @PostMapping("/{id}/payments")
    public ResponseEntity<Payment> postPayment(
            @PathVariable Long id,
            @Valid @RequestBody Payment payment,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationId) {
        Payment savedPayment = mortgageService.processPayment(id, payment);
        return new ResponseEntity<>(savedPayment, HttpStatus.CREATED);
    }

    @GetMapping("/{id}/payments")
    public ResponseEntity<List<Payment>> getPayments(@PathVariable Long id) {
        List<Payment> payments = mortgageService.getPaymentsByMortgage(id);
        return ResponseEntity.ok(payments);
    }
}