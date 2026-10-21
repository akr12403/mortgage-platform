package com.capstone.mortgage.controller;

import com.capstone.mortgage.dto.DelinquencyScanResponse;
import com.capstone.mortgage.service.DelinquencyService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Operational trigger for the daily delinquency batch (also runs on a schedule).
 * Will be restricted to ADMIN / SERVICING_AGENT once RBAC lands in M6.
 */
@RestController
@RequestMapping("/api/v1/delinquency-evaluations")
public class DelinquencyController {

    private final DelinquencyService delinquencyService;

    public DelinquencyController(DelinquencyService delinquencyService) {
        this.delinquencyService = delinquencyService;
    }

    @PostMapping
    public ResponseEntity<DelinquencyScanResponse> evaluate() {
        return ResponseEntity.ok(delinquencyService.evaluatePortfolio());
    }
}
