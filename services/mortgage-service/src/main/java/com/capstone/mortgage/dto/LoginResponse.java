package com.capstone.mortgage.dto;

import java.util.List;

/** Matches reference/sample-api-contracts.md: accessToken, expiresInSeconds, roles (+ tokenType). */
public record LoginResponse(String accessToken, String tokenType, long expiresInSeconds, List<String> roles) {}
