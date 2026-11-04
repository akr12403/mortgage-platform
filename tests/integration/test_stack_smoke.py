"""M9 Task 9.1 integration test: the running compose stack (the pipeline's own images) works end to end.

    python3 tests/integration/test_stack_smoke.py          # stdlib only; stack must be up (docker compose up -d)

1. every service is healthy;
2. a payment posted to mortgage-service is published (SNS) and consumed (SQS) by BOTH consumers:
   servicing-service records PAYMENT_POSTED in the servicing history, analytics counts a PaymentReceived event;
3. an idempotent replay of the same payment is not processed twice.
Reads AUTH_SEED_PASSWORD from the environment or the repo-root .env.
"""
import json
import os
import time
import unittest
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path

MS = os.getenv("MORTGAGE_API_BASE", "http://localhost:8080")
SS = os.getenv("SERVICING_API_BASE", "http://localhost:8081")
AS = os.getenv("ANALYTICS_API_BASE", "http://localhost:8000")
KA = os.getenv("ASSISTANT_API_BASE", "http://localhost:8001")
MORTGAGE = os.getenv("SMOKE_MORTGAGE", "MTG-1001")


def seed_password():
    if os.getenv("AUTH_SEED_PASSWORD"):
        return os.environ["AUTH_SEED_PASSWORD"]
    env_file = Path(__file__).resolve().parents[2] / ".env"
    for line in env_file.read_text().splitlines() if env_file.exists() else []:
        if line.startswith("AUTH_SEED_PASSWORD=") and line.split("=", 1)[1].strip():
            return line.split("=", 1)[1].strip()
    raise unittest.SkipTest("AUTH_SEED_PASSWORD is not set")


def call(method, url, token=None, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None), dict(resp.headers)
    except urllib.error.HTTPError as err:
        raw = err.read()
        return err.code, (json.loads(raw) if raw else None), dict(err.headers)


def login(user):
    status, body, _ = call("POST", f"{MS}/api/v1/auth/login", body={"username": user, "password": seed_password()})
    assert status == 200, (status, body)
    return body["accessToken"]


def wait_for(predicate, timeout=60, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


class StackSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servicing = login("servicing@capstone.local")
        cls.admin = login("admin@capstone.local")

    def test_1_all_services_healthy(self):
        for name, url in (("mortgage-service", f"{MS}/actuator/health"), ("servicing-service", f"{SS}/actuator/health"),
                          ("analytics-service", f"{AS}/health"), ("knowledge-assistant", f"{KA}/health")):
            with self.subTest(service=name):
                status, body, _ = call("GET", url)
                self.assertEqual(status, 200)
                self.assertEqual(body.get("status"), "UP")

    def _history_types(self):
        status, body, _ = call("GET", f"{SS}/api/v1/mortgages/{MORTGAGE}/servicing-history", self.servicing)
        self.assertEqual(status, 200)
        items = body["events"]  # ServicingHistoryResponse {mortgageExternalId, events: [{eventTime, eventType, ...}]}
        return [e["eventType"] for e in items]

    def _analytics_payments(self):
        status, body, _ = call("GET", f"{AS}/api/v1/analytics/event-stats", self.admin)
        self.assertEqual(status, 200)
        return (body.get("eventsProcessed") or {}).get("PaymentReceived", 0)

    def test_2_payment_event_reaches_both_consumers_once(self):
        before_history = self._history_types().count("PAYMENT_POSTED")
        before_analytics = self._analytics_payments()
        key = f"ci-smoke-{uuid.uuid4()}"
        payment = {"dueDate": str(date.today() - timedelta(days=2)), "paidDate": str(date.today()),
                   "amount": 1.00, "status": "POSTED"}
        status, body, headers = call("POST", f"{MS}/api/v1/mortgages/{MORTGAGE}/payments", self.servicing, payment,
                                     {"Idempotency-Key": key})
        self.assertEqual(status, 200, body)
        replay_status, _, replay_headers = call("POST", f"{MS}/api/v1/mortgages/{MORTGAGE}/payments", self.servicing,
                                                payment, {"Idempotency-Key": key})
        self.assertEqual(replay_status, 200)
        self.assertEqual({k.lower(): v for k, v in replay_headers.items()}.get("idempotent-replayed"), "true")

        history = wait_for(lambda: self._history_types().count("PAYMENT_POSTED") > before_history)
        self.assertTrue(history, "servicing-service did not record PAYMENT_POSTED within 60 s (SNS -> SQS -> consumer)")
        analytics = wait_for(lambda: self._analytics_payments() > before_analytics)
        self.assertTrue(analytics, "analytics-service did not consume PaymentReceived within 60 s")
        time.sleep(5)  # give a duplicate (if any) time to arrive
        self.assertEqual(self._history_types().count("PAYMENT_POSTED"), before_history + 1, "payment processed twice")


if __name__ == "__main__":
    unittest.main(verbosity=2)
