"""M8 Task 8.4: mortgage lookup by ID from DynamoDB (CapstoneMortgageLookup-dev), not PostgreSQL.

GET /api/v1/lookup/mortgages/{mortgageExternalId}
  200 cached status / balance / borrower business ID (no PII), with the item's freshness (updatedAt, lastEventType)
  404 NOT_FOUND            no item for that ID
  503 LOOKUP_UNAVAILABLE   DynamoDB not configured here (local LocalStack-only mode) or unreachable
"""
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from src.api.security import LOOKUP_READ, require_roles
from src.services.lookup_service import LookupUnavailableError, MortgageLookupStore

router = APIRouter(prefix="/api/v1/lookup", tags=["lookup"], dependencies=[Depends(require_roles(*LOOKUP_READ))])
logger = logging.getLogger(__name__)

_store = MortgageLookupStore()


def get_lookup_store() -> MortgageLookupStore:
    return _store


def _error(request: Request, status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={
        "code": code, "message": message,
        "correlationId": getattr(request.state, "correlation_id", None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/mortgages/{mortgage_external_id}")
def lookup_mortgage(request: Request,
                    mortgage_external_id: str = Path(..., pattern=r"^MTG-\d{4}$"),
                    store: MortgageLookupStore = Depends(get_lookup_store)):
    started = time.perf_counter()
    try:
        item = store.get(mortgage_external_id)
    except LookupUnavailableError as exc:
        logger.error("[%s] DynamoDB lookup unavailable: %s", getattr(request.state, "correlation_id", None), exc)
        raise _error(request, 503, "LOOKUP_UNAVAILABLE", "Mortgage lookup is temporarily unavailable")
    if item is None:
        raise _error(request, 404, "NOT_FOUND", f"Mortgage {mortgage_external_id} not found in the lookup table")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info("[%s] lookup %s from DynamoDB in %sms", getattr(request.state, "correlation_id", None),
                mortgage_external_id, elapsed_ms)
    return {**item, "lookupSource": "dynamodb", "lookupMs": elapsed_ms}
