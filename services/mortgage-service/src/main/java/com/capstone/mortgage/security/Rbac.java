package com.capstone.mortgage.security;

/**
 * Role groups for the RBAC matrix in docs/security/security-controls.md (M6 Task 6.2).
 * Role codes come from guides/standards.md and arrive in the JWT "roles" claim (Spring authority ROLE_<code>).
 * Keep this class, SecurityConfig and the matrix doc in sync; RbacMatrixTest fails if they drift.
 */
public final class Rbac {

    private Rbac() {}

    public static final String ADMIN = "ADMIN";
    public static final String UNDERWRITER = "UNDERWRITER";
    public static final String SERVICING_AGENT = "SERVICING_AGENT";
    public static final String RISK_ANALYST = "RISK_ANALYST";
    public static final String SUPPORT = "SUPPORT";

    /** Every platform role: read-only mortgage, payment and servicing views. */
    public static final String[] ALL_ROLES = {ADMIN, UNDERWRITER, SERVICING_AGENT, RISK_ANALYST, SUPPORT};

    /** Origination and underwriting: create borrowers/mortgages, record underwriting decisions. */
    public static final String[] ORIGINATION = {ADMIN, UNDERWRITER};

    /** Servicing writes: post payments, run delinquency evaluation, add servicing notes. */
    public static final String[] SERVICING_WRITE = {ADMIN, SERVICING_AGENT};

    /** Borrower PII (name, email, phone, date of birth): only roles that work with individual borrowers. */
    public static final String[] BORROWER_PII_READ = {ADMIN, UNDERWRITER, SERVICING_AGENT};
}
