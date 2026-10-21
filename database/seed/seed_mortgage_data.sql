-- Comprehensive Synthetic Seed Data for Mortgage Intelligence Platform
-- Target: Run after 001_core_schema.sql

-- 1. BORROWERS (5+ records)
INSERT INTO borrower (borrower_external_id, first_name, last_name, email, phone, date_of_birth) VALUES
  ('BOR-001', 'Jamie', 'Nguyen', 'jamie.nguyen@example.test', '+1-555-1001', '1985-03-20'),
  ('BOR-002', 'Morgan', 'Lee', 'morgan.lee@example.test', '+1-555-1002', '1990-11-02'),
  ('BOR-003', 'Taylor', 'Smith', 'taylor.smith@example.test', '+1-555-1003', '1978-07-15'),
  ('BOR-004', 'Jordan', 'Patel', 'jordan.patel@example.test', '+1-555-1004', '1992-12-05'),
  ('BOR-005', 'Alex', 'Johnson', 'alex.johnson@example.test', '+1-555-1005', '1983-05-28');

-- 2. MORTGAGES (10+ records with varied statuses: ACTIVE, DELINQUENT, CLOSED)
INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1001', id, 'ACTIVE', 310000.00, 305000.00, '2024-01-15' FROM borrower WHERE borrower_external_id = 'BOR-001';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1002', id, 'DELINQUENT', 280000.00, 279000.00, '2023-06-01' FROM borrower WHERE borrower_external_id = 'BOR-002';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1003', id, 'ACTIVE', 420000.00, 415000.00, '2024-03-10' FROM borrower WHERE borrower_external_id = 'BOR-003';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1004', id, 'ACTIVE', 250000.00, 240000.00, '2022-11-20' FROM borrower WHERE borrower_external_id = 'BOR-004';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1005', id, 'DELINQUENT', 350000.00, 348000.00, '2023-09-12' FROM borrower WHERE borrower_external_id = 'BOR-005';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1006', id, 'CLOSED', 200000.00, 0.00, '2015-04-10' FROM borrower WHERE borrower_external_id = 'BOR-001';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1007', id, 'ACTIVE', 480000.00, 472000.00, '2024-05-01' FROM borrower WHERE borrower_external_id = 'BOR-002';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1008', id, 'ACTIVE', 315000.00, 310000.00, '2024-02-18' FROM borrower WHERE borrower_external_id = 'BOR-003';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1009', id, 'CLOSED', 190000.00, 0.00, '2014-08-22' FROM borrower WHERE borrower_external_id = 'BOR-004';

INSERT INTO mortgage (mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date)
SELECT 'MTG-1010', id, 'ACTIVE', 390000.00, 385000.00, '2024-06-15' FROM borrower WHERE borrower_external_id = 'BOR-005';

-- 3. LOANS (Mapping 1:1 to Mortgages)
INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2001', m.id, 0.0625, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1001';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2002', m.id, 0.0700, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1002';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2003', m.id, 0.0585, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1003';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2004', m.id, 0.0550, 180, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1004';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2005', m.id, 0.0725, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1005';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2006', m.id, 0.0450, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1006';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2007', m.id, 0.0610, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1007';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2008', m.id, 0.0630, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1008';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2009', m.id, 0.0425, 180, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1009';

INSERT INTO loan (loan_external_id, mortgage_id, interest_rate, term_months, underwriting_decision)
SELECT 'LOAN-2010', m.id, 0.0650, 360, 'APPROVED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1010';

-- 4. DELINQUENCY (For delinquent scenarios: MTG-1002 and MTG-1005)
INSERT INTO delinquency (mortgage_id, delinquent_since, days_past_due, severity)
SELECT m.id, '2026-02-15', 45, 'MODERATE' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1002';

INSERT INTO delinquency (mortgage_id, delinquent_since, days_past_due, severity)
SELECT m.id, '2026-01-02', 88, 'SEVERE' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1005';  -- 60-89 DPD band

-- 5. PAYMENTS (Including scheduled, posted, and missed/delinquent scenarios)
INSERT INTO payment (mortgage_id, due_date, paid_date, amount, status)
SELECT m.id, '2026-02-01', '2026-02-03', 1750.00, 'POSTED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1001';

INSERT INTO payment (mortgage_id, due_date, paid_date, amount, status)
SELECT m.id, '2026-03-01', '2026-03-02', 1750.00, 'POSTED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1001';

INSERT INTO payment (mortgage_id, due_date, paid_date, amount, status)
SELECT m.id, '2026-02-01', NULL, 1650.00, 'FAILED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1002';

INSERT INTO payment (mortgage_id, due_date, paid_date, amount, status)
SELECT m.id, '2026-03-01', NULL, 1650.00, 'FAILED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1002';

INSERT INTO payment (mortgage_id, due_date, paid_date, amount, status)
SELECT m.id, '2026-03-01', '2026-03-01', 2100.00, 'POSTED' FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1003';

-- 6. SERVICING HISTORY EVENTS
INSERT INTO servicing_history (mortgage_id, event_time, event_type, description)
SELECT m.id, NOW() - INTERVAL '40 days', 'PAYMENT_POSTED', 'On-time monthly payment received via ACH.'
FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1001';

INSERT INTO servicing_history (mortgage_id, event_time, event_type, description)
SELECT m.id, NOW() - INTERVAL '25 days', 'DELINQUENCY_NOTICE_SENT', 'Generated 30-day past due collection letter.'
FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1002';

INSERT INTO servicing_history (mortgage_id, event_time, event_type, description)
SELECT m.id, NOW() - INTERVAL '15 days', 'ESCROW_ANALYSIS', 'Annual escrow analysis completed with minor surplus.'
FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1003';

-- 7. DOCUMENT METADATA ROWS
INSERT INTO document (mortgage_id, document_type, s3_key, file_name)
SELECT m.id, 'W2_FORM', 's3://mortgage-docs-bucket/mtg-1001/w2_2024.pdf', 'w2_2024.pdf'
FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1001';

INSERT INTO document (mortgage_id, document_type, s3_key, file_name)
SELECT m.id, 'TAX_RETURN', 's3://mortgage-docs-bucket/mtg-1002/tax_2024.pdf', 'tax_return_2024.pdf'
FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1002';

INSERT INTO document (mortgage_id, document_type, s3_key, file_name)
SELECT m.id, 'CLOSING_DISCLOSURE', 's3://mortgage-docs-bucket/mtg-1003/closing_disclosure.pdf', 'closing_disclosure.pdf'
FROM mortgage m WHERE m.mortgage_external_id = 'MTG-1003';