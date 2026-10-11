import pytest
from fastapi import HTTPException
from src.services.normalization_service import normalize_mortgages, normalize_payments, normalize_borrowers

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

def test_normalize_borrowers_missing_email():
    data = [{"id": 1, "borrower_external_id": "B-1", "first_name": "John", "last_name": "Smith", "email": None}]
    df = normalize_borrowers(data, correlation_id="test-corr-3")
    assert df.loc[0, "email"] == "unknown@example.test"

def test_normalize_payments_posted_without_date():
    data = [{"id": 1, "mortgage_id": 1, "status": "POSTED", "paid_date": None, "amount": 500.0}]
    with pytest.raises(HTTPException) as exc_info:
        normalize_payments(data, correlation_id="test-corr-4")
    assert exc_info.value.status_code == 400