import pytest
import pandas as pd
from src.analytics.portfolio import compute_portfolio_summary, compute_borrower_risk_summary, compute_payment_trends

def test_analytics_delinquency_rate():
    # Known dataset: 2 active, 1 delinquent -> 33.33% delinquency rate
    df = pd.DataFrame([
        {"mortgage_external_id": "MTG-1", "status": "ACTIVE", "outstanding_balance": 100000.0},
        {"mortgage_external_id": "MTG-2", "status": "ACTIVE", "outstanding_balance": 150000.0},
        {"mortgage_external_id": "MTG-3", "status": "DELINQUENT", "outstanding_balance": 200000.0}
    ])
    
    summary = compute_portfolio_summary(df)
    assert summary["total_mortgages"] == 3
    assert summary["delinquent_mortgages"] == 1
    assert summary["delinquency_rate"] == pytest.approx(0.3333, abs=1e-4)

def test_analytics_empty_portfolio():
    df = pd.DataFrame(columns=["status", "outstanding_balance"])
    summary = compute_portfolio_summary(df)
    assert summary["total_mortgages"] == 0
    assert summary["delinquency_rate"] == 0.0

def test_borrower_risk_summary():
    df_borrowers = pd.DataFrame([
        {"id": 1, "borrower_external_id": "B-100", "first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}
    ])
    df_mortgages = pd.DataFrame([
        {"borrower_id": 1, "status": "ACTIVE", "outstanding_balance": 150000.0}
    ])
    result = compute_borrower_risk_summary(df_borrowers, df_mortgages, "B-100")
    assert result["total_mortgages"] == 1
    assert result["total_outstanding_balance"] == 150000.0

def test_payment_trends():
    df_payments = pd.DataFrame([
        {"status": "POSTED", "paid_date": "2026-01-10", "due_date": "2026-01-15", "amount": 1200.0}
    ])
    trends = compute_payment_trends(df_payments, start_date="2026-01-01", end_date="2026-01-31")
    assert len(trends) == 1
    assert trends[0]["posted_amount"] == 1200.0