"""M10 Task 10.5 final demonstration (Session 36): one mortgage's life across the whole platform, ~25 minutes.

    python3 scripts/final-demo.py              # run straight through (~1 minute of API time)
    python3 scripts/final-demo.py --pause      # wait for Enter before each step (rehearsal / live demo)

Script and talking points: docs/operations/final-demo-script.md. Prerequisites: the stack and the local Splunk running
(bash scripts/splunk/local-up.sh), the knowledge base ingested, AUTH_SEED_PASSWORD and LLM_API_KEY in .env.

Every request in the demo carries the same correlation ID (final-demo-<hex>), so step 8 finds the whole story,
across all four services and the event consumers, with one Splunk search. The demo creates its own borrower and
mortgage; nothing in the seed data changes except one read. It makes 3 LLM calls (a few cents).
Writes reports/demo/<date>/final-demo-<time>.md: what each step showed, with UTC timestamps (the rehearsal log).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MS = os.getenv("MORTGAGE_API_BASE", "http://localhost:8080")
SS = os.getenv("SERVICING_API_BASE", "http://localhost:8081")
AS = os.getenv("ANALYTICS_API_BASE", "http://localhost:8000")
KA = os.getenv("ASSISTANT_API_BASE", "http://localhost:8001")
CID = f"final-demo-{uuid.uuid4().hex[:12]}"
LOG: list[str] = []
STARTED = datetime.now(timezone.utc)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def step(title: str, minutes: int, pause: bool) -> None:
    print(f"\n\033[1;36m== {title}  ({minutes} min) ==\033[0m")
    if pause:
        input("   (Enter to run) ")
    LOG.append(f"\n### {title}\n\n- {now()} UTC: started")


def say(text: str) -> None:
    print(f"   \033[2m{text}\033[0m")


def show(label: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(f"   {label}: {text}")
    LOG.append(f"- {label}: `{text[:300]}`")


def check(ok: bool, what: str) -> None:
    mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
    print(f"   {mark} {what}")
    LOG.append(f"- {'PASS' if ok else 'FAIL'}: {what}")
    if not ok:
        RESULTS["failed"] += 1


RESULTS = {"failed": 0}


def env_value(name: str, file: str = ".env") -> str:
    if os.getenv(name):
        return os.environ[name]
    path = ROOT / file
    for line in path.read_text().splitlines() if path.exists() else []:
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return ""


def call(method: str, url: str, token: str | None = None, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "X-Correlation-Id": CID,
        **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw, status, hdrs = resp.read(), resp.status, dict(resp.headers)
    except urllib.error.HTTPError as err:
        raw, status, hdrs = err.read(), err.code, dict(err.headers)
    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        payload = raw.decode(errors="replace")
    return status, payload, {k.lower(): v for k, v in hdrs.items()}


def login(user: str, password: str) -> str:
    status, body, _ = call("POST", f"{MS}/api/v1/auth/login", body={"username": f"{user}@capstone.local",
                                                                     "password": password})
    if status != 200:
        sys.exit(f"login failed for {user}@capstone.local: HTTP {status} (is the stack up? is .env right?)")
    return body["accessToken"]


def wait_for(read, done, timeout: float = 60):
    deadline = time.time() + timeout
    value = read()
    while not done(value) and time.time() < deadline:
        time.sleep(1)
        value = read()
    return value


def history(token: str, mortgage: str) -> list[str]:
    status, body, _ = call("GET", f"{SS}/api/v1/mortgages/{mortgage}/servicing-history", token)
    return [e["eventType"] for e in body["events"]] if status == 200 else []


def splunk_client():
    for line in (ROOT / ".env.splunk-local").read_text().splitlines() if (ROOT / ".env.splunk-local").exists() else []:
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)
    spec = importlib.util.spec_from_file_location("splunk_apply", ROOT / "scripts" / "splunk" / "apply.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Splunk()


def splunk_rows(splunk, query: str, earliest: str = "-30m") -> list[dict]:
    status, text = splunk.call("POST", "/services/search/jobs/export",
                               {"search": f"search {query}", "earliest_time": earliest, "latest_time": "now"},
                               timeout=120)
    if status != 200:
        return []
    return [json.loads(line)["result"] for line in text.splitlines() if '"result"' in line
            and not json.loads(line).get("preview", False)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pause", action="store_true", help="wait for Enter before each step")
    args = parser.parse_args()
    pause = args.pause or os.getenv("PAUSE") == "1"
    password = env_value("AUTH_SEED_PASSWORD")
    if not password:
        sys.exit("AUTH_SEED_PASSWORD is not set (environment or .env)")

    print(f"\033[1mMortgage Intelligence & Servicing Platform: final demonstration\033[0m  (correlationId {CID})")
    for name, url in (("mortgage-service", f"{MS}/actuator/health"), ("servicing-service", f"{SS}/actuator/health"),
                      ("analytics-service", f"{AS}/health"), ("knowledge-assistant", f"{KA}/health/ready")):
        status, _, _ = call("GET", url)
        say(f"{name}: {'UP' if status == 200 else f'NOT READY (HTTP {status})'}")
    tokens = {u: login(u, password) for u in ("underwriter", "servicing", "risk", "support", "admin")}

    # 1 ----------------------------------------------------------------------------------------------------------
    step("1. Onboarding: borrower and mortgage application", 3, pause)
    say("Underwriter registers a borrower, then a mortgage with a PENDING loan (US-BOR-001, US-MTG-001).")
    for _ in range(8):
        bid = f"BOR-{random.randint(500, 999)}"
        status, borrower, _ = call("POST", f"{MS}/api/v1/borrowers", tokens["underwriter"], {
            "borrowerExternalId": bid, "firstName": "Dana", "lastName": f"Demo{bid[4:]}",
            "email": f"dana.demo{bid[4:]}.{int(time.time())}@example.test", "phone": "+1-555-0142",
            "dateOfBirth": "1987-05-14"})
        if status != 409:
            break
    check(status == 201, f"POST /api/v1/borrowers -> {status}, borrower {bid}")
    for _ in range(8):
        mid, lid = f"MTG-{random.randint(5000, 9999)}", f"LOAN-{random.randint(5000, 9999)}"
        status, mortgage, _ = call("POST", f"{MS}/api/v1/mortgages", tokens["underwriter"], {
            "mortgageExternalId": mid, "borrowerExternalId": bid, "originalAmount": 320000.00,
            "outstandingBalance": 320000.00, "originationDate": str(date.today() - timedelta(days=400)),
            "loan": {"loanExternalId": lid, "interestRate": 0.0650, "termMonths": 360,
                     "underwritingDecision": "PENDING"}})
        if status != 409:
            break
    check(status == 201 and mortgage["status"] == "PENDING", f"POST /api/v1/mortgages -> {status}, {mid} PENDING")
    show("mortgage", {k: mortgage.get(k) for k in ("mortgageExternalId", "borrowerExternalId", "status",
                                                    "outstandingBalance")})

    # 2 ----------------------------------------------------------------------------------------------------------
    step("2. Underwriting decision (approval workflow)", 2, pause)
    say("Only ADMIN or UNDERWRITER may decide; the approver's role comes from the JWT, never from the request.")
    status, mortgage, _ = call("POST", f"{MS}/api/v1/mortgages/{mid}/underwriting-decision", tokens["underwriter"],
                               {"decision": "APPROVED"})
    check(status == 200 and mortgage["status"] == "ACTIVE", f"underwriting-decision APPROVED -> {status}, {mid} ACTIVE")
    types = wait_for(lambda: history(tokens["servicing"], mid), lambda t: "LOAN_APPROVED" in t)
    check({"MORTGAGE_CREATED", "LOAN_APPROVED"} <= set(types),
          f"servicing-service received MortgageCreated + LoanApproved via SNS -> SQS: {types}")

    # 3 ----------------------------------------------------------------------------------------------------------
    step("3. Payment, idempotency and the servicing history", 3, pause)
    say("Servicing agent posts the first installment with an Idempotency-Key, then the client retries it.")
    key = f"{CID}-pay-1"
    payment = {"dueDate": str(date.today() - timedelta(days=2)), "paidDate": str(date.today()), "amount": 1850.00,
               "status": "POSTED"}
    status, _, _ = call("POST", f"{MS}/api/v1/mortgages/{mid}/payments", tokens["servicing"], payment,
                        {"Idempotency-Key": key})
    check(status == 200, f"POST payment 1,850.00 -> {status}")
    status, _, headers = call("POST", f"{MS}/api/v1/mortgages/{mid}/payments", tokens["servicing"], payment,
                              {"Idempotency-Key": key})
    check(status == 200 and headers.get("idempotent-replayed") == "true",
          "same payment again, same key -> replayed, not posted twice (Idempotent-Replayed: true)")
    _, current, _ = call("GET", f"{MS}/api/v1/mortgages/{mid}", tokens["servicing"])
    check(float(current["outstandingBalance"]) == 318150.00, f"balance 320,000.00 -> {current['outstandingBalance']}")
    types = wait_for(lambda: history(tokens["servicing"], mid), lambda t: "PAYMENT_POSTED" in t)
    check(types.count("PAYMENT_POSTED") == 1, f"servicing history: {types}")

    # 4 ----------------------------------------------------------------------------------------------------------
    step("4. Missed payment -> delinquency", 3, pause)
    say("The installment due 45 days ago failed. 30+ days past due on an ACTIVE mortgage -> DELINQUENT (US-DEL-001).")
    status, _, _ = call("POST", f"{MS}/api/v1/mortgages/{mid}/payments", tokens["servicing"],
                        {"dueDate": str(date.today() - timedelta(days=45)), "amount": 1850.00, "status": "FAILED"},
                        {"Idempotency-Key": f"{CID}-pay-0"})
    _, current, _ = call("GET", f"{MS}/api/v1/mortgages/{mid}", tokens["servicing"])
    check(status == 200 and current["status"] == "DELINQUENT", f"FAILED installment -> {mid} {current['status']}")
    snap = wait_for(lambda: call("GET", f"{SS}/api/v1/mortgages/{mid}/delinquency", tokens["risk"])[1],
                    lambda b: isinstance(b, dict) and b.get("severity"))
    check(snap.get("status") == "DELINQUENT" and snap.get("severity") == "MODERATE",
          f"servicing-service snapshot from LoanDelinquent: {snap.get('daysPastDue')} days, {snap.get('severity')}")
    show("servicing history", history(tokens["servicing"], mid))

    # 5 ----------------------------------------------------------------------------------------------------------
    step("5. Analytics: portfolio, delinquency, borrower risk", 3, pause)
    say("analytics-service reads the same database and consumes the same events (risk analyst's view).")
    status, summary, _ = call("GET", f"{AS}/api/v1/analytics/portfolio-summary", tokens["risk"])
    check(status == 200, f"portfolio-summary -> {status}")
    show("portfolio", summary)
    status, delinquent, _ = call("GET", f"{AS}/api/v1/analytics/delinquency", tokens["risk"])
    rows = delinquent if isinstance(delinquent, list) else (delinquent or {}).get("items", delinquent)
    check(status == 200 and mid in json.dumps(rows), f"delinquency list -> {status}, includes {mid}")
    _, admin_view, _ = call("GET", f"{AS}/api/v1/analytics/borrowers/{bid}/risk-summary", tokens["admin"])
    _, risk_view, _ = call("GET", f"{AS}/api/v1/analytics/borrowers/{bid}/risk-summary", tokens["risk"])
    check("firstName" in (admin_view or {}) and "firstName" not in (risk_view or {}),
          "risk summary: ADMIN sees the borrower's name, RISK_ANALYST gets the same figures without it (need-to-know)")
    show("risk analyst's view", risk_view)
    status, stats, _ = call("GET", f"{AS}/api/v1/analytics/event-stats", tokens["risk"])
    show("events consumed by analytics", (stats or {}).get("eventsProcessed"))
    say("Dashboards: Splunk 'Mortgage Platform: Service Health' (browser); the M8 curated report via "
        "/api/v1/analytics/curated/delinquency-report.")

    # 6 ----------------------------------------------------------------------------------------------------------
    step("6. Security: unauthorized users are denied", 2, pause)
    status, body, _ = call("POST", f"{MS}/api/v1/mortgages/MTG-1001/underwriting-decision", tokens["support"],
                           {"decision": "APPROVED"})
    check(status == 403 and (body or {}).get("code") == "ACCESS_DENIED",
          f"SUPPORT approves MTG-1001 -> {status} {(body or {}).get('code')} (US-SEC-002)")
    status, body, _ = call("GET", f"{MS}/api/v1/borrowers/{bid}")
    check(status == 401, f"no token, GET borrower -> {status} {(body or {}).get('code')} (US-SEC-001)")
    status, body, _ = call("GET", f"{MS}/api/v1/borrowers/{bid}", tokens["support"])
    check(status == 403, f"SUPPORT reads borrower PII -> {status} {(body or {}).get('code')}")

    # 7 ----------------------------------------------------------------------------------------------------------
    step("7. Knowledge assistant: grounded answer with citations", 3, pause)
    question = "What happens when a mortgage payment is 30 days past due?"
    status, answer, _ = call("POST", f"{KA}/api/v1/assistant/ask", tokens["servicing"], {"question": question})
    cites = [f"{c['documentId']} / {c['section']}" for c in (answer or {}).get("citations", [])]
    check(status == 200 and cites, f"\"{question}\" -> {len(cites)} citation(s), confidence "
                                   f"{(answer or {}).get('confidence')}")
    print(f"   answer: {(answer or {}).get('answer', '')[:400]}")
    show("citations", cites)
    status, answer, _ = call("POST", f"{KA}/api/v1/assistant/ask", tokens["servicing"],
                             {"question": f"Should we approve a forbearance for {mid}?", "mortgageExternalId": mid})
    check(status == 200 and (answer or {}).get("requiresHumanApproval") is True,
          "acting on a specific case -> requiresHumanApproval: true (advisory only, a person decides)")
    status, answer, _ = call("POST", f"{KA}/api/v1/assistant/ask", tokens["servicing"],
                             {"question": "Who won the football world cup in 1998?"})
    check(status == 200 and (answer or {}).get("citations") == [],
          f"off-topic question -> no citations, confidence {(answer or {}).get('confidence')} (no invented answer)")

    # 8 ----------------------------------------------------------------------------------------------------------
    step("8. Splunk: the whole story by one correlation ID", 3, pause)
    query = f'index=mortgage_dev correlationId="{CID}"'
    say(query)
    try:
        splunk = splunk_client()
        rows = wait_for(lambda: splunk_rows(splunk, f"{query} | stats count by service.name"),
                        lambda r: len(r) >= 3, timeout=90)
        by_service = {r["service.name"]: int(r["count"]) for r in rows}
        check(len(by_service) >= 3, f"log lines by service for this demo: {by_service}")
        routes = splunk_rows(splunk, f'{query} message=http_request | stats count by service.name, http.method, '
                                     'http.route, http.status | sort service.name')
        for r in routes[:14]:
            print(f"   {r['service.name']:<22} {r['http.method']:<5} {r['http.route']:<52} {r['http.status']} x{r['count']}")
        events = splunk_rows(splunk, f'{query} message!=http_request service.name=servicing-service | head 5 '
                                     '| table message')
        show("servicing-service consumer lines (same correlationId, carried in the events)",
             [e.get("message", "")[:80] for e in events])
    except SystemExit as exc:
        say(f"Splunk not reachable ({exc}); run the search above in the browser.")
        LOG.append("- Splunk not reachable from the script; search shown in the browser")

    # 9 ----------------------------------------------------------------------------------------------------------
    step("9. Operations: incident, runbook, readiness", 3, pause)
    try:
        fired = splunk_rows(splunk, 'index=_audit action=alert_fired ss_name="mortgage_dev - *" '
                                    '| stats earliest(_time) as first by ss_name | sort first', earliest="-30d")
        for r in fired:
            print(f"   alert fired: {r['ss_name']}  first {datetime.fromtimestamp(float(r['first']), timezone.utc):%Y-%m-%d %H:%M}Z")
        LOG.append(f"- alerts fired (30 days): {len(fired)}")
    except (NameError, SystemExit):
        say("alerts: Splunk Activity -> Triggered Alerts")
    say("RCA 2026-11-10 (database outage): detection 1 min 4 s -> 40 s, failures 30 s/500 -> 3 s/503 after the fixes.")
    say("Runbook: docs/operations/runbook.md (alerts, common failures, rollback); readiness: GO with conditions.")
    say("Pipeline: build, tests, gates, scans, integration + E2E J1-J5, publish: gh run list --workflow ci -L 1")

    # ------------------------------------------------------------------------------------------------------------
    total = sum(1 for line in LOG if line.startswith("- PASS") or line.startswith("- FAIL"))
    verdict = "all checks passed" if RESULTS["failed"] == 0 else f"{RESULTS['failed']} check(s) FAILED"
    print(f"\n\033[1;{'32' if RESULTS['failed'] == 0 else '31'}mDemo complete: {total} checks, {verdict}.\033[0m "
          f"Borrower {bid}, mortgage {mid}, correlationId {CID}")
    out = ROOT / "reports" / "demo" / STARTED.strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"final-demo-{STARTED:%H%M%S}.md"
    path.write_text(f"# Final demo run {STARTED:%Y-%m-%dT%H:%M:%SZ}\n\ncorrelationId `{CID}`, borrower {bid}, "
                    f"mortgage {mid}. Finished {now()} UTC: {total} checks, {verdict}.\n" + "\n".join(LOG) + "\n")
    print(f"Run log: {path.relative_to(ROOT)}")
    sys.exit(1 if RESULTS["failed"] else 0)


if __name__ == "__main__":
    main()
