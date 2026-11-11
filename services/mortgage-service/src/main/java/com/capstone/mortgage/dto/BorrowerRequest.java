package com.capstone.mortgage.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;

public record BorrowerRequest(
        @NotBlank @Pattern(regexp = "BOR-\\d{3}", message = "must match BOR-{3 digits}") String borrowerExternalId,
        @NotBlank @Size(max = 100) String firstName,
        @NotBlank @Size(max = 100) String lastName,
        @NotBlank @Email @Size(max = 255) String email,
        @Pattern(regexp = "\\+?[0-9 ()-]{7,30}", message = "must be a phone number (7-30 digits, spaces, +, -, parentheses)") String phone,
        @Past LocalDate dateOfBirth
) {}
