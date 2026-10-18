from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text  # <-- Make sure this is included!
from src.api.dependencies import get_db
from src.repositories.mortgage_repository import MortgageRepository
from src.services.normalization_service import normalize_mortgages, normalize_borrowers, normalize_payments
from src.analytics.portfolio import compute_portfolio_summary, compute_borrower_risk_summary, compute_payment_trends

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

import traceback
import logging

logger = logging.getLogger(__name__)

@router.get("/portfolio-summary")
def get_portfolio_summary(request: Request, db: Session = Depends(get_db)):
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        repo = MortgageRepository(db)
        
        mortgages_query = db.execute(text("SELECT id, mortgage_external_id, status, outstanding_balance FROM mortgages")).fetchall()
        raw_list = [dict(row._mapping) for row in mortgages_query]
        
        norm_df = normalize_mortgages(raw_list, correlation_id=correlation_id)
        summary = compute_portfolio_summary(norm_df)
        return summary
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[{correlation_id}] Portfolio summary error: {tb}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "traceback": tb,
                "correlationId": correlation_id
            }
        )

@router.get("/delinquency")
def get_delinquencies(request: Request, db: Session = Depends(get_db)):
    correlation_id = getattr(request.state, "correlation_id", None)
    repo = MortgageRepository(db)
    delinquencies = repo.get_delinquencies()
    return {"delinquent_mortgages": delinquencies, "count": len(delinquencies)}

@router.get("/borrowers/{borrower_external_id}/risk-summary")
def get_borrower_risk(borrower_external_id: str, request: Request, db: Session = Depends(get_db)):
    correlation_id = getattr(request.state, "correlation_id", None)
    repo = MortgageRepository(db)
    
    borrower_res = repo.get_borrower_risk_summary(borrower_external_id)
    if not borrower_res:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": f"Borrower {borrower_external_id} not found",
                "correlationId": correlation_id
            }
        )
    return borrower_res

@router.get("/payment-trends")
def get_payment_trends(
    request: Request,
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    db: Session = Depends(get_db)
):
    correlation_id = getattr(request.state, "correlation_id", None)
    repo = MortgageRepository(db)
    trends = repo.get_payment_trends(from_date, to_date)
    return {"trends": trends}