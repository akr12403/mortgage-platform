-- ============================================================================
-- Milestone 2 - Task 2.5: SQL Lab Artifacts & Mortgage Operations Queries
-- ============================================================================

-- 1. Borrower-to-Loan Join
-- Retrieves borrower details alongside their mortgage and loan structural terms.
SELECT 
    b.borrower_external_id,
    b.first_name || ' ' || b.last_name AS borrower_name,
    m.mortgage_external_id,
    m.status AS mortgage_status,
    l.loan_external_id,
    l.interest_rate,
    l.term_months
FROM borrower b
JOIN mortgage m ON b.id = m.borrower_id
JOIN loan l ON m.id = l.mortgage_id;

-- 2. Outstanding Balance Aggregation
-- Aggregates total portfolio exposure and average balances grouped by mortgage status.
SELECT 
    status,
    COUNT(*) AS mortgage_count,
    SUM(original_amount) AS total_original_exposure,
    SUM(outstanding_balance) AS total_outstanding_balance,
    ROUND(AVG(outstanding_balance), 2) AS average_outstanding_balance
FROM mortgage
GROUP BY status;

-- 3. Delinquent Loans Report
-- Identifies active delinquencies, days past due, severity levels, and borrower contact info.
SELECT 
    m.mortgage_external_id,
    b.first_name || ' ' || b.last_name AS borrower_name,
    b.phone,
    m.outstanding_balance,
    d.days_past_due,
    d.severity,
    d.delinquent_since
FROM mortgage m
JOIN borrower b ON m.borrower_id = b.id
JOIN delinquency d ON m.id = d.mortgage_id
ORDER BY d.days_past_due DESC;

-- 4. Slow Query Scenario & Index Optimization
-- Unoptimized/Slow Scenario: Searching servicing history audit logs by date range 
-- without an index forces a full table sequential scan (Seq Scan).
-- 
-- EXPLAIN ANALYZE 
-- SELECT * FROM servicing_history WHERE event_time >= NOW() - INTERVAL '30 days';
-- 
-- Optimization Fix: Create a B-tree index on event_time to convert Seq Scan to Index Scan.
-- CREATE INDEX idx_servicing_history_event_time ON servicing_history(event_time);