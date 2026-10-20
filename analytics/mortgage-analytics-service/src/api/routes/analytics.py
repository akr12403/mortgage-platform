from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from src.api.dependencies import get_db
from src.repositories.mortgage_repository import MortgageRepository
from datetime import datetime, timezone
import logging

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

logger = logging.getLogger(__name__)


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])

@router.get("/portfolio-summary")
def get_portfolio_summary(request: Request, db: Session = Depends(get_db)):
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        repo = MortgageRepository(db)
        summary = repo.get_portfolio_summary()
        return {_camel_case(key): value for key, value in summary.items()}
    except Exception:
        logger.exception("[%s] Portfolio summary query failed", correlation_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Unable to retrieve portfolio summary",
                "correlationId": correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

@router.get("/delinquency")
def get_delinquencies(request: Request, db: Session = Depends(get_db)):
    correlation_id = getattr(request.state, "correlation_id", None)
    repo = MortgageRepository(db)
    delinquencies = repo.get_delinquencies()
    return {
        "delinquentMortgages": [
            {_camel_case(key): value for key, value in item.items()}
            for item in delinquencies
        ],
        "count": len(delinquencies)
    }

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
    return {_camel_case(key): value for key, value in borrower_res.items()}

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
    return {
        "from": from_date,
        "to": to_date,
        "buckets": [
            {_camel_case(key): value for key, value in item.items()}
            for item in trends
        ]
    }