"""Generate realistic API traffic against the local stack so the Splunk dashboard, SLIs and alerts have data
(M9 Tasks 9.3, 9.4). Stdlib only.

    python3 scripts/splunk/traffic.py                  # 3 minutes, ~2 requests/s
    python3 scripts/splunk/traffic.py --minutes 15 --workers 6   # incident drill: requests may hang 30 s

Each loop, as the servicing user: list a borrower's mortgages, read one, post a 1.00 payment (unique Idempotency-Key), read its
servicing history; as admin: analytics event stats. Every request gets its own X-Correlation-ID. Payments go to the
local development database only (amount 1.00, the same as tests/integration/test_stack_smoke.py).
Reads AUTH_SEED_PASSWORD from the environment or the repo-root .env; never prints it.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

MS = os.getenv("MORTGAGE_API_BASE", "http://localhost:8080")
SS = os.getenv("SERVICING_API_BASE", "http://localhost:8081")
AS = os.getenv("ANALYTICS_API_BASE", "http://localhost:8000")
MORTGAGES = ["MTG-1001", "MTG-1002", "MTG-1003"]


def seed_password() -> str:
    if os.getenv("AUTH_SEED_PASSWORD"):
        return os.environ["AUTH_SEED_PASSWORD"]
    env = Path(__file__).resolve().parents[2] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("AUTH_SEED_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("AUTH_SEED_PASSWORD is not set (environment or .env)")


def call(method: str, url: str, token: str | None = None, body: dict | None = None,
         headers: dict | None = None) -> tuple[int, dict | None]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "X-Correlation-ID": f"traffic-{uuid.uuid4()}",
        **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        return err.code, None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0, None  # connection refused / timeout: counted as "no response"


def login(user: str, password: str) -> str:
    status, body = call("POST", f"{MS}/api/v1/auth/login", body={"username": user, "password": password})
    if status != 200:
        raise SystemExit(f"login as {user} failed with HTTP {status}: is the stack up?")
    return body["accessToken"]


def worker(n: int, deadline: float, rate: float, servicing: str, admin: str, stats: Counter,
           lock: threading.Lock) -> None:
    i = n  # workers start at different steps, so they don't all hit the same endpoint at once
    while time.time() < deadline:
        mortgage = MORTGAGES[i % len(MORTGAGES)]
        step = i % 5
        payment_status = None
        if step == 0:
            status, _ = call("GET", f"{MS}/api/v1/mortgages?borrowerId=BOR-001&page=0&size=5", servicing)
        elif step == 1:
            status, _ = call("GET", f"{MS}/api/v1/mortgages/{mortgage}", servicing)
        elif step == 2:
            payment = {"dueDate": str(date.today() - timedelta(days=1)), "paidDate": str(date.today()),
                       "amount": 1.00, "status": "POSTED"}
            status, _ = call("POST", f"{MS}/api/v1/mortgages/{mortgage}/payments", servicing, payment,
                             {"Idempotency-Key": f"traffic-{uuid.uuid4()}"})
            payment_status = status
        elif step == 3:
            status, _ = call("GET", f"{SS}/api/v1/mortgages/{mortgage}/servicing-history", servicing)
        else:
            status, _ = call("GET", f"{AS}/api/v1/analytics/event-stats", admin)
        with lock:
            stats["5xx" if status >= 500 else "no response" if status == 0 else f"{status // 100}xx"] += 1
            stats["requests"] += 1
            if payment_status is not None:
                stats[f"payment {payment_status or 'no response'}"] += 1
        i += 1
        time.sleep(1 / rate)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=3)
    parser.add_argument("--rate", type=float, default=2.0, help="requests per second per worker (approximate)")
    parser.add_argument("--workers", type=int, default=1,
                        help="parallel clients; use several when requests may hang (incident drill)")
    args = parser.parse_args()
    password = seed_password()
    servicing, admin = login("servicing@capstone.local", password), login("admin@capstone.local", password)
    stats: Counter = Counter()
    lock = threading.Lock()
    deadline = time.time() + args.minutes * 60
    print(f"Sending traffic for {args.minutes:g} min: {args.workers} worker(s) at ~{args.rate:g} req/s each "
          f"(Ctrl-C to stop)", flush=True)
    threads = [threading.Thread(target=worker, args=(n, deadline, args.rate, servicing, admin, stats, lock),
                                daemon=True) for n in range(args.workers)]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(30)
            with lock:
                print(f"  {time.strftime('%H:%M:%S')} {dict(sorted(stats.items()))}", flush=True)
    except KeyboardInterrupt:
        pass
    with lock:
        print(f"Done: {dict(sorted(stats.items()))}", flush=True)


if __name__ == "__main__":
    main()
