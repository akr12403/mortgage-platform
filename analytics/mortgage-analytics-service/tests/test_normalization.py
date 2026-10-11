import pytest
import pandas as pd
from src.analytics.portfolio import normalize_portfolio_data  # Adjust import based on your actual function name

def test_normalization_bad_status():
    data = pd.DataFrame([
        {"mortgage_external_id": "MTG-999", "status": "UNKNOWN_STATUS", "outstanding_balance": 150000.0}
    ])
    # Assuming normalization filters out or flags bad statuses
    normalized = normalize_portfolio_data(data)
    assert "UNKNOWN_STATUS" not in normalized["status"].values

def test_normalization_negative_balance():
    data = pd.DataFrame([
        {"mortgage_external_id": "MTG-998", "status": "ACTIVE", "outstanding_balance": -5000.0}
    ])
    with pytest.raises(ValueError, match="balance"):
        normalize_portfolio_data(data)