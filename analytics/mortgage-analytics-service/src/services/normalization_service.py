import pandas as pd
import logging
from fastapi import HTTPException
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

ALLOWED_MORTGAGE_STATUSES = {"PENDING", "ACTIVE", "DELINQUENT", "CLOSED", "FORECLOSURE"}
ALLOWED_PAYMENT_STATUSES = {"SCHEDULED", "POSTED", "FAILED", "REVERSED"}

def normalize_borrowers(raw_borrowers: List[Dict[Any, Any]], correlation_id: str = None) -> pd.DataFrame:
    if not raw_borrowers:
        return pd.DataFrame(columns=["id", "borrower_external_id", "first_name", "last_name", "email", "phone"])
    
    df = pd.DataFrame(raw_borrowers)
    
    # Handle missing emails (default to unknown@example.test in dev)
    missing_email_mask = df["email"].isna() | (df["email"] == "")
    if missing_email_mask.any():
        logger.warning(f"[{correlation_id}] Missing email detected for {missing_email_mask.sum()} borrower(s). Defaulting to unknown@example.test.")
        df.loc[missing_email_mask, "email"] = "unknown@example.test"
        
    return df

def normalize_mortgages(raw_mortgages: List[Dict[Any, Any]], correlation_id: str = None) -> pd.DataFrame:
    if not raw_mortgages:
        return pd.DataFrame(columns=["id", "mortgage_external_id", "status", "outstanding_balance"])
    
    df = pd.DataFrame(raw_mortgages)
    
    # Validate outstanding balance >= 0
    invalid_balance = df["outstanding_balance"] < 0
    if invalid_balance.any():
        logger.error(f"[{correlation_id}] Validation failure: Negative outstanding balance detected.")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Outstanding balance cannot be negative",
                "correlationId": correlation_id
            }
        )
        
    # Validate status against allowed enums
    invalid_status = ~df["status"].isin(ALLOWED_MORTGAGE_STATUSES)
    if invalid_status.any():
        logger.error(f"[{correlation_id}] Validation failure: Invalid mortgage status detected.")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Invalid mortgage status found. Allowed: {list(ALLOWED_MORTGAGE_STATUSES)}",
                "correlationId": correlation_id
            }
        )
        
    return df

def normalize_payments(raw_payments: List[Dict[Any, Any]], correlation_id: str = None) -> pd.DataFrame:
    if not raw_payments:
        return pd.DataFrame(columns=["id", "mortgage_id", "due_date", "paid_date", "amount", "status"])
        
    df = pd.DataFrame(raw_payments)
    
    # Validate paid_date is required if status is POSTED
    posted_without_date = (df["status"] == "POSTED") & df["paid_date"].isna()
    if posted_without_date.any():
        logger.error(f"[{correlation_id}] Validation failure: POSTED payment missing paid_date.")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "paid_date is required for POSTED payments",
                "correlationId": correlation_id
            }
        )
        
    return df