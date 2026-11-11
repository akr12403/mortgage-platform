package com.capstone.mortgage.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * Approval workflow stub (M5 Task 5.3). Since M6 Task 6.2 the deciding role is taken from the caller's JWT
 * (UNDERWRITER, else ADMIN) — the client can no longer claim a role in the body. Unknown fields are ignored.
 */
public record UnderwritingDecisionRequest(
        @NotBlank @Pattern(regexp = "APPROVED|DECLINED", message = "must be APPROVED or DECLINED") String decision
) {}
