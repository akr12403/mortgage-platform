package com.capstone.mortgage.dto;

import java.time.Instant;
import java.util.List;

public record DelinquencyScanResponse(Instant evaluatedAt, int mortgagesTransitioned, List<Transition> transitions) {
    public record Transition(String mortgageExternalId, String delinquentSince, long daysPastDue, String severity) {}
}
