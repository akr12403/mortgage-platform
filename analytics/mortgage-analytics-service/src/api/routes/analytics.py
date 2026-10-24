from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from src.api.dependencies import get_db
from src.api.security import ANALYTICS_READ, BORROWER_PII_READ, Principal, current_principal, require_roles
from src.repositories.mortgage_repository import MortgageRepository
from datetime import date, datetime, timezone
import logging

# RBAC (M6 Task 6.2): every analytics route requires ADMIN, UNDERWRITER or RISK_ANALYST.
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"],
                   dependencies=[Depends(require_roles(*ANALYTICS_READ))])

logger = logging.getLogger(__name__)

# Task 6.3: bound the payment-trends scan (OWASP API4).
MAX_TREND_RANGE_DAYS = 3660

# Columns of the risk summary that identify the borrower (see docs/security/security-controls.md classification).
PII_COLUMNS = frozenset({"first_name", "last_name"})


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
def get_borrower_risk(request: Request,
                      borrower_external_id: str = Path(..., pattern=r"^BOR-\d{3}$"),
                      principal: Principal = Depends(current_principal),
                      db: Session = Depends(get_db)):
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
    # DP-GAP-1 (M6 Task 6.6): names are Confidential PII. Only BORROWER_PII_READ roles get them;
    # RISK_ANALYST works with the business ID and the financial aggregates.
    if not set(principal.roles).intersection(BORROWER_PII_READ):
        borrower_res = {k: v for k, v in borrower_res.items() if k not in PII_COLUMNS}
    return {_camel_case(key): value for key, value in borrower_res.items()}

@router.get("/payment-trends")
def get_payment_trends(
    request: Request,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db)
):
    correlation_id = getattr(request.state, "correlation_id", None)
    # Task 6.3: typed ISO dates (bad input -> 400 VALIDATION_ERROR) and a bounded range.
    if from_date > to_date:
        raise HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR",
                                                     "message": "from must be on or before to",
                                                     "correlationId": correlation_id})
    if (to_date - from_date).days > MAX_TREND_RANGE_DAYS:
        raise HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR",
                                                     "message": f"date range is limited to {MAX_TREND_RANGE_DAYS} days",
                                                     "correlationId": correlation_id})
    repo = MortgageRepository(db)
    trends = repo.get_payment_trends(from_date.isoformat(), to_date.isoformat())
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "buckets": [
            {_camel_case(key): value for key, value in item.items()}
            for item in trends
        ]
    }


@router.get("/event-stats")
def get_event_stats(request: Request):
    """Lifecycle events consumed from capstone-mortgage-analytics-dev and the refreshed snapshot."""
    processor = getattr(request.app.state, "analytics_processor", None)
    if processor is None:
        return {"consumerEnabled": False}
    return jsonable_encoder({"consumerEnabled": True, **processor.stats()})
