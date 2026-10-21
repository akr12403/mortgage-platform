package com.capstone.mortgage.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * Approval workflow stub (M5 Task 5.3). Real role checks arrive with JWT/RBAC in M6;
 * until then the caller states the role that made the decision.
 */
public record UnderwritingDecisionRequest(
        @NotBlank @Pattern(regexp = "APPROVED|DECLINED", message = "must be APPROVED or DECLINED") String decision,
        @Pattern(regexp = "ADMIN|UNDERWRITER", message = "must be ADMIN or UNDERWRITER") String decidedByRole
) {
    public String roleOrDefault() {
        return decidedByRole == null || decidedByRole.isBlank() ? "UNDERWRITER" : decidedByRole;
    }
}
