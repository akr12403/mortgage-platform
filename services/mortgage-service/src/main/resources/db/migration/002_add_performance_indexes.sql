-- Migration: Add performance indexes for foreign keys and lookup columns

CREATE INDEX IF NOT EXISTS idx_mortgages_borrower_id ON mortgages(borrower_id);

CREATE INDEX IF NOT EXISTS idx_payments_mortgage_id ON payments(mortgage_id);

CREATE INDEX IF NOT EXISTS idx_servicing_history_mortgage_id ON servicing_history(mortgage_id);