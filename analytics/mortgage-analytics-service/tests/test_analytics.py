import pytest
import pandas as pd
from src.analytics.portfolio import compute_portfolio_summary

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