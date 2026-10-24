-- Migration for idempotent event consumption deduplication
CREATE TABLE IF NOT EXISTS event_inbox (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);