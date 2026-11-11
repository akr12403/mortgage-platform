"""M10 Task 10.4 performance smoke: baseline latency and throughput of the running stack (not a load test).

    python3 scripts/perf/smoke.py                       # 2 min, 4 read workers + 1 payment writer, then 5 event-lag
                                                         # samples and 5 assistant questions
    python3 scripts/perf/smoke.py --seconds 60 --workers 2 --no-assistant

What it measures, client side (wall time per request, from this machine):
  * reads: mortgage, borrower's mortgages, payments, servicing history, delinquency, portfolio summary;
  * writes: payments (0.5/s, under the 60 writes/min per-user limit) on a mortgage created for this run;
  * event lag: payment accepted -> PAYMENT_POSTED visible in servicing-service (SNS -> SQS -> consumer);
  * assistant: grounded answers through the real LLM (skip with --no-assistant).
Targets: payment p95 < 500 ms (docs/operations/slo.md), portfolio summary < 2 s (US-ANL-001), every request 2xx,
event lag < 60 s (the candidate event SLO). Writes reports/perf/<date>/perf-smoke.{json,md} (git-ignored).
Only seed reads and new data for this run: the payments go to a mortgage the script creates.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MS = os.getenv("MORTGAGE_API_BASE", "http://localhost:8080")
SS = os.getenv("SERVICING_API_BASE", "http://localhost:8081")
AS = os.getenv("ANALYTICS_API_BASE", "http://localhost:8000")
KA = os.getenv("ASSISTANT_API_BASE", "http://localhost:8001")
RUN = f"perf-{uuid.uuid4().hex[:8]}"

READS = [  # (name, base, path, user)
    ("GET mortgage", MS, "/api/v1/mortgages/MTG-1001", "servicing"),
    ("GET borrower's mortgages", MS, "/api/v1/mortgages?borrowerId=BOR-001", "servicing"),
    ("GET payments", MS, "/api/v1/mortgages/MTG-1001/payments", "servicing"),
    ("GET servicing history", SS, "/api/v1/mortgages/MTG-1001/servicing-history", "servicing"),
    ("GET delinquency", SS, "/api/v1/mortgages/MTG-1002/delinquency", "risk"),
    ("GET portfolio summary", AS, "/api/v1/analytics/portfolio-summary", "risk"),
]
TARGETS_MS = {"POST payment": 500, "GET portfolio summary": 2000}
QUESTIONS = [
    "What happens when a mortgage payment is 30 days past due?",
    "When is a second underwriting review required?",
    "How do I check whether a loan is delinquent?",
    "What severity does a loan 65 days past due have?",
    "Who can approve a forbearance request?",
]


def seed_password() -> str:
    if os.getenv("AUTH_SEED_PASSWORD"):
        return os.environ["AUTH_SEED_PASSWORD"]
    env = ROOT / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("AUTH_SEED_PASSWORD=") and line.split("=", 1)[1].strip():
            return line.split("=", 1)[1].strip()
    raise SystemExit("AUTH_SEED_PASSWORD is not set (environment or repo-root .env)")


def call(method: str, url: str, token: str | None = None, body: dict | None = None,
         headers: dict | None = None) -> tuple[int, object, float]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "X-Correlation-Id": f"{RUN}-{uuid.uuid4().hex[:12]}",
        **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as err:
        raw, status = err.read(), err.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None, (time.perf_counter() - start) * 1000
    elapsed = (time.perf_counter() - start) * 1000
    try:
        return status, (json.loads(raw) if raw else None), elapsed
    except ValueError:
        return status, None, elapsed


def login(username: str, password: str) -> str:
    status, body, _ = call("POST", f"{MS}/api/v1/auth/login", body={"username": username, "password": password})
    if status != 200:
        raise SystemExit(f"login failed for {username}: HTTP {status}")
    return body["accessToken"]


class Results:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.samples: dict[str, list[float]] = {}
        self.statuses: dict[str, dict[int, int]] = {}

    def add(self, name: str, status: int, ms: float) -> None:
        with self.lock:
            self.samples.setdefault(name, []).append(ms)
            counts = self.statuses.setdefault(name, {})
            counts[status] = counts.get(status, 0) + 1

    def table(self, seconds: float) -> list[dict]:
        rows = []
        for name in sorted(self.samples):
            values = sorted(self.samples[name])
            ok = sum(n for s, n in self.statuses[name].items() if 200 <= s < 300)
            rows.append({"endpoint": name, "requests": len(values), "per_second": round(len(values) / seconds, 1),
                         "non_2xx": len(values) - ok, "statuses": self.statuses[name],
                         "p50_ms": pct(values, 50), "p95_ms": pct(values, 95), "p99_ms": pct(values, 99),
                         "max_ms": round(values[-1], 1), "target_p95_ms": TARGETS_MS.get(name)})
        return rows


def pct(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    index = min(len(sorted_values), max(1, math.ceil(p / 100 * len(sorted_values)))) - 1
    return round(sorted_values[index], 1)


def create_mortgage(underwriter: str) -> str:
    for _ in range(8):
        bid, mid = f"BOR-{random.randint(500, 999)}", f"MTG-{random.randint(5000, 9999)}"
        status, _, _ = call("POST", f"{MS}/api/v1/borrowers", underwriter, {
            "borrowerExternalId": bid, "firstName": "Perf", "lastName": f"Smoke{bid[4:]}",
            "email": f"perf.smoke{bid[4:]}.{int(time.time())}@example.test"})
        if status == 409:
            continue
        status, body, _ = call("POST", f"{MS}/api/v1/mortgages", underwriter, {
            "mortgageExternalId": mid, "borrowerExternalId": bid, "originalAmount": 250000,
            "outstandingBalance": 250000, "originationDate": str(date.today() - timedelta(days=400)),
            "loan": {"loanExternalId": f"LOAN-{random.randint(5000, 9999)}", "interestRate": 0.065,
                     "termMonths": 360, "underwritingDecision": "APPROVED"}})
        if status == 201:
            return body["mortgageExternalId"]
    raise SystemExit("could not create the run's mortgage")


def payment(token: str, mortgage: str, results: Results | None = None) -> tuple[int, float]:
    status, _, ms = call("POST", f"{MS}/api/v1/mortgages/{mortgage}/payments", token,
                         {"dueDate": str(date.today()), "paidDate": str(date.today()), "amount": 1.00,
                          "status": "POSTED"}, {"Idempotency-Key": f"{RUN}-{uuid.uuid4()}"})
    if results:
        results.add("POST payment", status, ms)
    return status, ms


def history_count(token: str, mortgage: str) -> int:
    status, body, _ = call("GET", f"{SS}/api/v1/mortgages/{mortgage}/servicing-history", token)
    return sum(e["eventType"] == "PAYMENT_POSTED" for e in body["events"]) if status == 200 else -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--workers", type=int, default=4, help="parallel read clients")
    parser.add_argument("--no-assistant", action="store_true")
    args = parser.parse_args()

    password = seed_password()
    tokens = {u: login(f"{u}@capstone.local", password) for u in ("servicing", "risk", "underwriter")}
    mortgage = create_mortgage(tokens["underwriter"])
    started = datetime.now(timezone.utc)
    print(f"Perf smoke {RUN}: {args.seconds:g} s, {args.workers} read workers + 1 payment writer "
          f"(0.5/s on {mortgage}), from {started:%Y-%m-%dT%H:%M:%SZ}")

    results = Results()
    deadline = time.time() + args.seconds

    def reader(n: int) -> None:
        i = n
        while time.time() < deadline:
            name, base, path, user = READS[i % len(READS)]
            status, _, ms = call("GET", base + path, tokens[user])
            results.add(name, status, ms)
            i += 1

    def writer() -> None:
        while time.time() < deadline:
            payment(tokens["servicing"], mortgage, results)
            time.sleep(2)

    threads = [threading.Thread(target=reader, args=(n,)) for n in range(args.workers)]
    threads.append(threading.Thread(target=writer))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    load = results.table(args.seconds)

    # Event lag: one payment at a time, poll servicing-service until it shows up.
    lags = []
    time.sleep(5)  # let the load's events drain first
    for _ in range(5):
        before = history_count(tokens["servicing"], mortgage)
        status, _ = payment(tokens["servicing"], mortgage)
        accepted = time.perf_counter()
        while status == 200 and time.perf_counter() - accepted < 60:
            if history_count(tokens["servicing"], mortgage) > before:
                lags.append(round((time.perf_counter() - accepted) * 1000))
                break
            time.sleep(0.1)
        else:
            lags.append(None)
        time.sleep(2)

    assistant = []
    if not args.no_assistant:
        for question in QUESTIONS:
            status, body, ms = call("POST", f"{KA}/api/v1/assistant/ask", tokens["servicing"], {"question": question})
            assistant.append({"question": question, "status": status, "ms": round(ms),
                              "citations": len((body or {}).get("citations", [])) if isinstance(body, dict) else 0})

    report = {"run": RUN, "started": f"{started:%Y-%m-%dT%H:%M:%SZ}", "seconds": args.seconds,
              "read_workers": args.workers, "mortgage": mortgage, "load": load,
              "event_lag_ms": lags, "assistant": assistant}
    out = ROOT / "reports" / "perf" / started.strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    (out / "perf-smoke.json").write_text(json.dumps(report, indent=2))

    lines = [f"Perf smoke {RUN}, {report['started']}, {args.seconds:g} s, {args.workers} read workers + "
             "1 payment writer (0.5/s)", "",
             "| Endpoint | Requests | Req/s | Non-2xx | p50 ms | p95 ms | p99 ms | Max ms | Target p95 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in load:
        target = f"< {r['target_p95_ms']} ms {'met' if r['p95_ms'] < r['target_p95_ms'] else 'MISSED'}" \
            if r["target_p95_ms"] else ""
        lines.append(f"| {r['endpoint']} | {r['requests']} | {r['per_second']} | {r['non_2xx']} | {r['p50_ms']} | "
                     f"{r['p95_ms']} | {r['p99_ms']} | {r['max_ms']} | {target} |")
    total = sum(r["requests"] for r in load)
    lines += ["", f"Total: {total} requests, {round(total / args.seconds, 1)}/s, "
              f"{sum(r['non_2xx'] for r in load)} non-2xx.",
              f"Event lag (payment accepted -> PAYMENT_POSTED in servicing history), ms: {lags}"]
    if assistant:
        ms = sorted(a["ms"] for a in assistant)
        lines.append(f"Assistant (real LLM, {len(assistant)} questions): median {ms[len(ms) // 2]} ms, max {ms[-1]} ms, "
                     f"statuses {[a['status'] for a in assistant]}, citations {[a['citations'] for a in assistant]}")
    (out / "perf-smoke.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWritten: {out.relative_to(ROOT)}/perf-smoke.md, perf-smoke.json")


if __name__ == "__main__":
    main()
