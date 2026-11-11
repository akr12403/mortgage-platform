package com.capstone.servicing.dto;

/** Matches reference/sample-api-contracts.md GET /api/v1/mortgages/{id}/delinquency. */
public record DelinquencyResponse(
        String mortgageExternalId,
        String status,
        String delinquentSince,
        Integer daysPastDue,
        String severity
) {}
