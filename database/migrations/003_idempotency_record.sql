-- M4/M5: payment Idempotency-Key support (mortgage-service owns this table).
-- Idempotent: safe to re-run on existing volumes (applied by the db-migrate compose service).
CREATE TABLE IF NOT EXISTS idempotency_record (
    idempotency_key     VARCHAR(255) PRIMARY KEY,
    request_fingerprint TEXT        NOT NULL,
    payment_id          UUID        NOT NULL REFERENCES payment(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
