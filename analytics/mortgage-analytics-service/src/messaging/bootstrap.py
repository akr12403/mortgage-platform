"""Starts the optional analytics SQS consumer when SQS_QUEUE_ANALYTICS_EVENTS is configured."""
from __future__ import annotations

import logging
import os
from typing import Optional

from src.messaging.event_consumer import AnalyticsEventProcessor, SqsAnalyticsConsumer

logger = logging.getLogger(__name__)


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def refresh_portfolio_snapshot() -> dict:
    """Recomputes the portfolio summary from PostgreSQL (the 'analytics refresh' an event triggers)."""
    from src.api.dependencies import SessionLocal
    from src.repositories.mortgage_repository import MortgageRepository

    with SessionLocal() as session:
        summary = MortgageRepository(session).get_portfolio_summary()
    return {_camel_case(key): (float(value) if hasattr(value, "is_finite") else value) for key, value in summary.items()}


def start_analytics_consumer(app) -> Optional[SqsAnalyticsConsumer]:
    queue_url = os.getenv("SQS_QUEUE_ANALYTICS_EVENTS", "").strip()
    enabled = os.getenv("ANALYTICS_CONSUMER_ENABLED", "true").lower() == "true"
    app.state.analytics_processor = None
    if not queue_url or not enabled:
        logger.info("Analytics event consumer disabled (SQS_QUEUE_ANALYTICS_EVENTS not set or disabled)")
        return None

    import boto3  # imported lazily so unit tests do not need AWS libraries

    sqs = boto3.client(
        "sqs",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None,
    )
    processor = AnalyticsEventProcessor(refresh_portfolio_snapshot)
    consumer = SqsAnalyticsConsumer(
        queue_url=queue_url,
        processor=processor,
        sqs_client=sqs,
        max_receive_count=int(os.getenv("SQS_MAX_RECEIVE_COUNT", "3")),
    )
    app.state.analytics_processor = processor
    consumer.start()
    return consumer
