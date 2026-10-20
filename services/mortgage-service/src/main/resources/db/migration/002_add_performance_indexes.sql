-- Migration: Add performance indexes for foreign keys and lookup columns

CREATE INDEX IF NOT EXISTS idx_mortgage_borrower ON mortgage(borrower_id);
CREATE INDEX IF NOT EXISTS idx_mortgage_status ON mortgage(status);
CREATE INDEX IF NOT EXISTS idx_payment_mortgage_due ON payment(mortgage_id, due_date);
CREATE INDEX IF NOT EXISTS idx_servicing_mortgage_time ON servicing_history(mortgage_id, event_time);