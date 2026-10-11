import pytest
from fastapi import HTTPException
from src.services.normalization_service import normalize_mortgages

def test_normalization_bad_status():
    data = [
        {"id": 1, "mortgage_external_id": "MTG-999", "status": "UNKNOWN_STATUS", "outstanding_balance": 150000.0}
    ]
    with pytest.raises(HTTPException) as exc_info:
        normalize_mortgages(data, correlation_id="test-corr-1")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "VALIDATION_ERROR"

def test_normalization_negative_balance():
    data = [
        {"id": 2, "mortgage_external_id": "MTG-998", "status": "ACTIVE", "outstanding_balance": -5000.0}
    ]
    with pytest.raises(HTTPException) as exc_info:
        normalize_mortgages(data, correlation_id="test-corr-2")
    assert exc_info.value.status_code == 400
    assert "balance" in exc_info.value.detail["message"].lower()