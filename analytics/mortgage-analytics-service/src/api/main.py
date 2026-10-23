import os
import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from src.api.routes import analytics, documents
from src.messaging.bootstrap import start_analytics_consumer
from src.api.security import validate_settings

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s service=mortgage-analytics-service - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()  # fail fast if JWT_SECRET is missing/short
    consumer = start_analytics_consumer(app)
    yield
    if consumer is not None:
        consumer.stop()


app = FastAPI(title="Mortgage Analytics Service", version="1.0.0", lifespan=lifespan)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    detail = exc.detail
    if isinstance(detail, dict):
        error_payload = {
            **detail,
            "correlationId": detail.get("correlationId", correlation_id),
            "timestamp": detail.get("timestamp", datetime.now(timezone.utc).isoformat())
        }
    else:
        error_payload = {
            "code": "HTTP_ERROR",
            "message": str(detail),
            "correlationId": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    return JSONResponse(status_code=exc.status_code, content=error_payload, headers=getattr(exc, "headers", None))

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.exception("Unhandled request error; correlationId=%s", correlation_id)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "correlationId": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )

@app.get("/health")
def health_check():
    return {"status": "UP", "service": "mortgage-analytics-service"}

# Include analytics router
app.include_router(analytics.router)
app.include_router(documents.router)