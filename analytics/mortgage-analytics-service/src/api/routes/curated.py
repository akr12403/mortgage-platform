"""M8 Task 8.5: delinquency report from the curated zone of the data lake (not from PostgreSQL).

GET /api/v1/analytics/curated/delinquency-report[?date=YYYY-MM-DD]   (latest partition when date is omitted)
GET /api/v1/analytics/curated/delinquency-report/dates               (available partitions)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.security import ANALYTICS_READ, require_roles
from src.services.curated_report import (CuratedNotFoundError, CuratedReportReader, CuratedSchemaError,
                                         CuratedUnavailableError)

router = APIRouter(prefix="/api/v1/analytics/curated", tags=["analytics"],
                   dependencies=[Depends(require_roles(*ANALYTICS_READ))])
logger = logging.getLogger(__name__)
_reader = CuratedReportReader()


def get_curated_reader() -> CuratedReportReader:
    return _reader


def _error(request: Request, status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={
        "code": code, "message": message, "correlationId": getattr(request.state, "correlation_id", None),
        "timestamp": datetime.now(timezone.utc).isoformat()})


def _guard(request: Request, fn):
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        return fn()
    except CuratedNotFoundError:
        raise _error(request, 404, "NOT_FOUND", "No curated delinquency report for that date")
    except CuratedSchemaError as exc:
        logger.error("[%s] curated schema mismatch: %s", correlation_id, exc)
        raise _error(request, 502, "CURATED_SCHEMA_MISMATCH", "The curated report does not match the expected schema")
    except CuratedUnavailableError as exc:
        logger.error("[%s] curated zone unavailable: %s", correlation_id, exc)
        raise _error(request, 503, "CURATED_UNAVAILABLE", "The curated data zone is temporarily unavailable")


@router.get("/delinquency-report")
def delinquency_report(request: Request,
                       date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                       reader: CuratedReportReader = Depends(get_curated_reader)):
    return _guard(request, lambda: reader.report(date))


@router.get("/delinquency-report/dates")
def delinquency_report_dates(request: Request, reader: CuratedReportReader = Depends(get_curated_reader)):
    return {"dates": _guard(request, reader.available_dates)}
