import pytest
import pandas as pd
from src.analytics.portfolio import compute_portfolio_metrics

def test_analytics_delinquency_rate():
    # Known dataset: 2 active, 1 delinquent -> 33.33% delinquency rate
    df = pd.DataFrame([
        {"mortgage_external_id": "MTG-1", "status": "ACTIVE", "outstanding_balance": 100000.0, "delinquent": False},
        {"mortgage_external_id": "MTG-2", "status": "ACTIVE", "outstanding_balance": 150000.0, "delinquent": False},
        {"mortgage_external_id": "MTG-3", "status": "DELINQUENT", "outstanding_balance": 200000.0, "delinquent": True}
    ])
    
    metrics = compute_portfolio_metrics(df)
    assert metrics["total_mortgages"] == 3
    assert metrics["delinquency_rate"] == pytest.approx(0.3333, abs=1e-4)