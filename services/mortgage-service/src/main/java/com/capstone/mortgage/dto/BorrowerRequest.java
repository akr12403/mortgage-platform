package com.capstone.mortgage.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.Pattern;

import java.time.LocalDate;

public record BorrowerRequest(
        @NotBlank @Pattern(regexp = "BOR-\\d{3}", message = "must match BOR-{3 digits}") String borrowerExternalId,
        @NotBlank String firstName,
        @NotBlank String lastName,
        @NotBlank @Email String email,
        String phone,
        @Past LocalDate dateOfBirth
) {}
