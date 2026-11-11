import pandas as pd
import numpy as np

def compute_portfolio_summary(df_mortgages: pd.DataFrame) -> dict:
    if df_mortgages.empty:
        return {
            "total_mortgages": 0,
            "active_mortgages": 0,
            "delinquent_mortgages": 0,
            "outstanding_balance_total": 0.0,
            "delinquency_rate": 0.0
        }
    
    total_mortgages = len(df_mortgages)
    active_mortgages = int((df_mortgages["status"] == "ACTIVE").sum())
    delinquent_mortgages = int((df_mortgages["status"] == "DELINQUENT").sum())
    outstanding_balance_total = float(df_mortgages["outstanding_balance"].sum())
    
    # Canonical rule (guides/standards.md): DELINQUENT / (ACTIVE + DELINQUENT).
    # PENDING and CLOSED mortgages are excluded from the denominator.
    servicing_population = active_mortgages + delinquent_mortgages
    delinquency_rate = float(delinquent_mortgages / servicing_population) if servicing_population > 0 else 0.0

    return {
        "total_mortgages": total_mortgages,
        "active_mortgages": active_mortgages,
        "delinquent_mortgages": delinquent_mortgages,
        "outstanding_balance_total": outstanding_balance_total,
        "delinquency_rate": round(delinquency_rate, 4)
    }

def compute_borrower_risk_summary(df_borrowers: pd.DataFrame, df_mortgages: pd.DataFrame, borrower_external_id: str) -> dict:
    # Filter borrower
    borrower_match = df_borrowers[df_borrowers["borrower_external_id"] == borrower_external_id]
    if borrower_match.empty:
        return None
    
    borrower = borrower_match.iloc[0]
    
    # Merge or filter mortgages associated with this borrower ID
    # Assuming df_mortgages has borrower_id matching df_borrowers id
    borrower_mortgages = df_mortgages[df_mortgages["borrower_id"] == borrower["id"]] if "borrower_id" in df_mortgages.columns else pd.DataFrame()
    
    if borrower_mortgages.empty:
        return {
            "borrower_external_id": borrower_external_id,
            "first_name": borrower["first_name"],
            "last_name": borrower["last_name"],
            "total_mortgages": 0,
            "total_outstanding_balance": 0.0,
            "delinquent_count": 0
        }
        
    total_mortgages = len(borrower_mortgages)
    total_balance = float(borrower_mortgages["outstanding_balance"].sum())
    delinquent_count = int((borrower_mortgages["status"] == "DELINQUENT").sum())
    
    return {
        "borrower_external_id": borrower_external_id,
        "first_name": borrower["first_name"],
        "last_name": borrower["last_name"],
        "total_mortgages": total_mortgages,
        "total_outstanding_balance": total_balance,
        "delinquent_count": delinquent_count
    }

def compute_payment_trends(df_payments: pd.DataFrame, start_date: str = None, end_date: str = None) -> list:
    if df_payments.empty:
        return []
        
    df = df_payments.copy()
    df["paid_date"] = pd.to_datetime(df["paid_date"])
    
    if start_date:
        df = df[df["paid_date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["paid_date"] <= pd.to_datetime(end_date)]
        
    posted_payments = df[df["status"] == "POSTED"].copy()
    if posted_payments.empty:
        return []
        
    # Compute on-time flag: paid_date <= due_date
    posted_payments["due_date"] = pd.to_datetime(posted_payments["due_date"])
    posted_payments["is_on_time"] = posted_payments["paid_date"] <= posted_payments["due_date"]
    
    # Group by monthly period using pd.Grouper or dt accessor
    grouper = posted_payments.groupby(pd.Grouper(key="paid_date", freq="ME"))
    
    trends = []
    for period, group in grouper:
        if group.empty:
            continue
        trends.append({
            "period": period.strftime("%Y-%m"),
            "posted_amount": float(group["amount"].sum()),
            "on_time_rate": float(group["is_on_time"].mean())
        })
        
    return trends