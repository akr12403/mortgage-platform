-- M6 Task 6.1: application users for JWT login (mortgage-service owns this table).
-- Passwords are stored ONLY as BCrypt hashes. No hashes or passwords are committed: mortgage-service
-- seeds the five standard users at startup from the AUTH_SEED_PASSWORD env var (see docs/security/authentication.md).
-- Idempotent: safe to re-run on existing volumes (applied by the db-migrate compose service).
CREATE TABLE IF NOT EXISTS app_user (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL,
    roles         VARCHAR(200) NOT NULL,
    enabled       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_app_user_roles CHECK (
        roles ~ '^(ADMIN|UNDERWRITER|SERVICING_AGENT|RISK_ANALYST|SUPPORT)(,(ADMIN|UNDERWRITER|SERVICING_AGENT|RISK_ANALYST|SUPPORT))*$'
    )
);
