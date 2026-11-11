package com.capstone.servicing.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ServicingEventRequest(
        @NotBlank @Pattern(regexp = "[A-Z][A-Z0-9_]{2,49}", message = "eventType must be UPPER_SNAKE_CASE") String eventType,
        @Size(max = 2000) String description
) {}
