"""M9 Task 9.4 incident simulation: PostgreSQL outage under traffic, detected and triaged in Splunk.

    bash scripts/splunk/local-up.sh                 # local Splunk + stack with log shipping must be running
    python3 scripts/incident/db_outage_drill.py     # ~15 min: 3 baseline, 6 outage, then recovery
    python3 scripts/incident/db_outage_drill.py --baseline 2 --outage 5 --after 4

What it does (every step timestamped in UTC):
  1. starts traffic (scripts/splunk/traffic.py, 6 parallel workers: requests hang ~30 s while the DB is down)
  2. after the baseline: INJECT  docker compose stop postgres
  3. while the DB is down: polls Splunk for the alerts as they fire (detection time per alert)
  4. after the outage window: RECOVER  docker compose start postgres, waits until it is healthy
  5. polls Splunk for the first successful payment after recovery (service recovered)
  6. exports the evidence from Splunk: payments per minute, first/last 5xx and errors per service, the trace of
     one failed payment by correlationId, the alerts that fired
Writes reports/incident/<date>/timeline.md and evidence.md (git-ignored: raw evidence). The RCA
(docs/operations/rca-<date>.md) is written from them. Only the local stack is touched.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAYMENTS = ('index=mortgage_dev message=http_request service.name=mortgage-service http.method=POST '
            'http.route="/api/v1/mortgages/{id}/payments"')
ALERT_PREFIX = "mortgage_dev - "


def load_local_env() -> None:
    import os
    env = ROOT / ".env.splunk-local"
    if not env.exists():
        sys.exit("run bash scripts/splunk/local-up.sh first (.env.splunk-local missing)")
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def splunk_client():
    spec = importlib.util.spec_from_file_location("splunk_apply", ROOT / "scripts" / "splunk" / "apply.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Splunk()


def utc(epoch: float | None = None) -> str:
    return datetime.fromtimestamp(epoch if epoch is not None else time.time(), timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


class Drill:
    def __init__(self, out: Path):
        self.splunk = splunk_client()
        self.out = out
        self.events: list[tuple[float, str]] = []

    def mark(self, what: str, at: float | None = None) -> float:
        at = at if at is not None else time.time()
        self.events.append((at, what))
        print(f"  {utc(at)}  {what}", flush=True)
        return at

    def search(self, query: str, earliest: float, latest: float | None = None) -> list[dict]:
        status, text = self.splunk.call("POST", "/services/search/jobs/export", {
            "search": query if query.lstrip().startswith("|") else f"search {query}",
            "earliest_time": f"{earliest:.0f}", "latest_time": f"{latest:.0f}" if latest else "now"}, timeout=180)
        if status != 200:
            raise RuntimeError(f"Splunk search failed: HTTP {status}: {text[:200]}")
        rows = []
        for line in text.splitlines():
            if '"result"' in line:
                result = json.loads(line).get("result")
                if result and not json.loads(line).get("preview", False):
                    rows.append(result)
        return rows

    def fired_alerts(self) -> dict[str, float]:
        """Alert name -> earliest trigger time, from Splunk's triggered-alerts list (alert.track = 1)."""
        fired: dict[str, float] = {}
        status, text = self.splunk.call("GET", "/servicesNS/-/-/alerts/fired_alerts?count=0")
        if status != 200:
            return fired
        for group in json.loads(text).get("entry", []):
            name = group.get("name", "")
            if not name.startswith(ALERT_PREFIX):
                continue
            path = "/servicesNS/-/-/alerts/fired_alerts/" + urllib.parse.quote(name, safe="") + "?count=0"
            status, detail = self.splunk.call("GET", path)
            if status != 200:
                continue
            for instance in json.loads(detail).get("entry", []):
                trigger = instance.get("content", {}).get("trigger_time")
                if trigger:
                    fired[name] = min(fired.get(name, float(trigger)), float(trigger))
        return fired


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def postgres_healthy() -> bool:
    out = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", "capstone-postgres"],
                         capture_output=True, text=True)
    return out.stdout.strip() == "healthy"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=float, default=3, help="minutes of normal traffic before the failure")
    parser.add_argument("--outage", type=float, default=6, help="minutes the database stays down")
    parser.add_argument("--after", type=float, default=4, help="minutes of traffic after recovery")
    args = parser.parse_args()
    load_local_env()
    out = ROOT / "reports" / "incident" / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    drill = Drill(out)
    drill.splunk.wait_ready(60)
    if not postgres_healthy():
        sys.exit("postgres is not healthy: start the stack first (bash scripts/splunk/local-up.sh)")

    print("\n== Incident drill: PostgreSQL outage (all times UTC) ==")
    start = drill.mark("drill start: traffic begins (6 workers)")
    minutes = args.baseline + args.outage + args.after + 1
    traffic_log = (out / "traffic.log").open("w")
    inject = float("inf")  # set when the failure is injected
    traffic = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "splunk" / "traffic.py"),
                                "--minutes", str(minutes), "--workers", "6", "--rate", "1"],
                               cwd=ROOT, stdout=traffic_log, stderr=subprocess.STDOUT)
    try:
        time.sleep(args.baseline * 60)
        inject = drill.mark("INJECT: docker compose stop postgres")
        compose("stop", "postgres")
        detected: dict[str, float] = {}
        while time.time() < inject + args.outage * 60:
            time.sleep(30)
            for name, at in sorted(drill.fired_alerts().items(), key=lambda kv: kv[1]):
                if at >= inject and name not in detected:
                    detected[name] = at
                    drill.mark(f"ALERT FIRED: {name[len(ALERT_PREFIX):]}", at)
        recover = drill.mark("RECOVER: docker compose start postgres")
        compose("start", "postgres")
        while not postgres_healthy():
            time.sleep(2)
        drill.mark("postgres healthy")
        deadline = time.time() + 300
        while time.time() < deadline:
            time.sleep(15)
            rows = drill.search(f"{PAYMENTS} http.status<500 | stats min(_time) as first", recover)
            if rows and rows[0].get("first"):
                drill.mark("service recovered: first successful payment after recovery", float(rows[0]["first"]))
                break
        traffic.wait()
    finally:
        if traffic.poll() is None:
            traffic.terminate()
        traffic_log.close()
        if not postgres_healthy():
            subprocess.run(["docker", "compose", "start", "postgres"], cwd=ROOT)
    end = drill.mark("traffic finished")
    time.sleep(60)  # let the last lines reach the index
    for name, at in drill.fired_alerts().items():  # alerts that fired after the outage window closed
        if at >= inject and not any(name[len(ALERT_PREFIX):] in what for _, what in drill.events):
            drill.mark(f"ALERT FIRED: {name[len(ALERT_PREFIX):]}", at)

    print("\n== Evidence from Splunk ==")
    evidence = {
        "payments_per_minute": drill.search(
            f"{PAYMENTS} | bin _time span=1m | stats count as total, count(eval('http.status'>=500)) as failed, "
            "perc95(durationMs) as p95_ms by _time | eval minute=strftime(_time, \"%H:%M\"), p95_ms=round(p95_ms,0) "
            "| table minute total failed p95_ms", start, end + 60),
        "payment_totals": drill.search(
            f"{PAYMENTS} | stats count as total, count(eval('http.status'>=500)) as failed, "
            "perc95(durationMs) as p95_ms, max(durationMs) as max_ms", start, end + 60),
        "five_xx_by_service": drill.search(
            "index=mortgage_dev message=http_request http.status>=500 | stats count, min(_time) as first, "
            "max(_time) as last by service.name | eval first=strftime(first, \"%Y-%m-%dT%H:%M:%SZ\"), "
            "last=strftime(last, \"%Y-%m-%dT%H:%M:%SZ\")", start, end + 60),
        "errors_by_service": drill.search(
            "index=mortgage_dev log.level=ERROR | stats count, min(_time) as first, max(_time) as last, "
            "values(error.type) as error_types by service.name | eval first=strftime(first, \"%Y-%m-%dT%H:%M:%SZ\"), "
            "last=strftime(last, \"%Y-%m-%dT%H:%M:%SZ\")", start, end + 60),
    }
    sample = drill.search(f"{PAYMENTS} http.status>=500 | head 1 | table correlationId", start, end + 60)
    if sample:
        cid = sample[0]["correlationId"]
        evidence["failed_payment_trace"] = drill.search(
            f'index=mortgage_dev correlationId="{cid}" | sort _time | eval t=strftime(_time, "%H:%M:%S") '
            '| table t service.name log.level message error.type http.status durationMs', start, end + 60)
        evidence["failed_payment_correlation_id"] = cid
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2))

    timeline = ["| Time (UTC) | Event |", "| --- | --- |"] + [f"| {utc(t)} | {w} |" for t, w in sorted(drill.events)]
    (out / "timeline.md").write_text("\n".join(timeline) + "\n")
    lines = ["# Evidence (Splunk, index mortgage_dev)", ""]
    for key, rows in evidence.items():
        lines += [f"## {key}", "", "```json", json.dumps(rows, indent=2), "```", ""]
    (out / "evidence.md").write_text("\n".join(lines))
    print("\n".join(timeline))
    print(f"\nPayment totals: {json.dumps(evidence['payment_totals'])}")
    print(f"Traffic: {(out / 'traffic.log').read_text().strip().splitlines()[-1]}")
    print(f"\nWritten: {out.relative_to(ROOT)}/timeline.md, evidence.md, evidence.json, traffic.log")


if __name__ == "__main__":
    main()
