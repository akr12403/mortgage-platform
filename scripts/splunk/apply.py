"""Apply monitoring/splunk/ (dashboard + alerts) to a Splunk instance through its REST API; with --local-setup also
create index mortgage_dev and the HEC token (local Splunk only). Idempotent: existing objects are updated.

    python3 scripts/splunk/apply.py --local-setup      # called by scripts/splunk/local-up.sh
    python3 scripts/splunk/apply.py                    # dashboard + alerts only
    python3 scripts/splunk/apply.py --search 'index=mortgage_dev correlationId="…"'   # run a search, print results

Connection from the environment (never from arguments, so nothing lands in shell history):
    SPLUNK_MGMT_URL         default https://127.0.0.1:8089 (TLS verification is skipped only for 127.0.0.1/localhost)
    SPLUNK_ADMIN_USER       default admin
    SPLUNK_ADMIN_PASSWORD   or SPLUNK_LOCAL_ADMIN_PASSWORD (written by local-up.sh to .env.splunk-local)
    SPLUNK_HEC_TOKEN        --local-setup only: the token value to register
Stdlib only.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLUNK_DIR = ROOT / "monitoring" / "splunk"
INDEX = os.getenv("SPLUNK_INDEX", "mortgage_dev")
SOURCETYPE = "mortgage:app:json"
APP = "search"
HEC_TOKEN_NAME = "mortgage-platform"


class Splunk:
    def __init__(self):
        self.base = os.getenv("SPLUNK_MGMT_URL", "https://127.0.0.1:8089").rstrip("/")
        user = os.getenv("SPLUNK_ADMIN_USER", "admin")
        password = os.getenv("SPLUNK_ADMIN_PASSWORD") or os.getenv("SPLUNK_LOCAL_ADMIN_PASSWORD")
        if not password:
            sys.exit("SPLUNK_ADMIN_PASSWORD (or SPLUNK_LOCAL_ADMIN_PASSWORD) is not set")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        host = urllib.parse.urlparse(self.base).hostname
        self.ctx = ssl.create_default_context()
        if host in ("127.0.0.1", "localhost"):  # local Splunk: self-signed certificate
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def call(self, method: str, path: str, data: dict | None = None, timeout: int = 60) -> tuple[int, str]:
        body = urllib.parse.urlencode({**(data or {}), "output_mode": "json"}).encode() if method == "POST" else None
        url = self.base + path + ("" if method == "POST" else ("&" if "?" in path else "?") + "output_mode=json")
        req = urllib.request.Request(url, data=body, method=method, headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=timeout) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    def upsert(self, collection: str, name: str, fields: dict) -> str:
        """Create, or update when it already exists (409). Returns 'created' / 'updated'."""
        status, text = self.call("POST", collection, {"name": name, **fields})
        if status in (200, 201):
            return "created"
        if status == 409:
            status, text = self.call("POST", f"{collection}/{urllib.parse.quote(name, safe='')}", fields)
            if status in (200, 201):
                return "updated"
        raise SystemExit(f"{collection} {name}: HTTP {status}: {text[:300]}")

    def wait_ready(self, seconds: int) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                if self.call("GET", "/services/server/info", timeout=10)[0] == 200:
                    return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(10)
        sys.exit(f"Splunk management API not ready after {seconds} s at {self.base}")


def local_setup(splunk: Splunk) -> None:
    token = os.getenv("SPLUNK_HEC_TOKEN") or sys.exit("SPLUNK_HEC_TOKEN is not set")
    status, text = splunk.call("POST", "/services/data/indexes", {"name": INDEX})
    if status not in (200, 201, 409):
        sys.exit(f"index {INDEX}: HTTP {status}: {text[:300]}")
    print(f"  index {INDEX}: {'exists' if status == 409 else 'created'}")
    status, text = splunk.call("POST", "/servicesNS/nobody/splunk_httpinput/data/inputs/http/http",
                               {"disabled": "0", "enableSSL": "1"})
    if status not in (200, 201):
        sys.exit(f"enable HEC: HTTP {status}: {text[:300]}")
    # The token may write ONLY to mortgage_dev; the value comes from .env.splunk-local and is never printed.
    collection = "/servicesNS/nobody/splunk_httpinput/data/inputs/http"
    fields = {"index": INDEX, "indexes": INDEX, "sourcetype": SOURCETYPE, "disabled": "0"}
    status, text = splunk.call("POST", collection, {"name": HEC_TOKEN_NAME, "token": token, **fields})
    if status == 409:  # exists: update the settings (a token value can't be changed in place)
        entity = urllib.parse.quote(f"http://{HEC_TOKEN_NAME}", safe="")
        status, text = splunk.call("POST", f"{collection}/{entity}", fields)
        state = "updated"
    else:
        state = "created"
    if status not in (200, 201):
        sys.exit(f"HEC token {HEC_TOKEN_NAME}: HTTP {status}: {text[:300]}")
    print(f"  HEC token {HEC_TOKEN_NAME}: {state} (index {INDEX} only, sourcetype {SOURCETYPE})")


def apply_monitoring(splunk: Splunk) -> None:
    views = f"/servicesNS/nobody/{APP}/data/ui/views"
    for xml in sorted((SPLUNK_DIR / "dashboards").glob("*.xml")):
        state = splunk.upsert(views, xml.stem, {"eai:data": xml.read_text()})
        print(f"  dashboard {xml.stem}: {state}")
    searches = f"/servicesNS/nobody/{APP}/saved/searches"
    for alert in json.loads((SPLUNK_DIR / "alerts.json").read_text())["alerts"]:
        fields = {
            "search": alert["search"],
            "description": f"{alert['description']} Runbook: {alert['runbook']}",
            "is_scheduled": "1", "cron_schedule": "* * * * *",
            "dispatch.earliest_time": alert.get("window", "-5m@m"), "dispatch.latest_time": "@m",
            "alert_type": "number of events", "alert_comparator": "greater than", "alert_threshold": "0",
            "alert.track": "1", "alert.severity": str(alert["severity"]), "alert.digest_mode": "1",
            "alert.suppress": "1", "alert.suppress.period": "10m", "disabled": "0",
        }
        print(f"  alert '{alert['name']}': {splunk.upsert(searches, alert['name'], fields)}")
    # Visible to everyone in the app (default would be private to admin).
    for kind, name in [("data/ui/views", p.stem) for p in (SPLUNK_DIR / "dashboards").glob("*.xml")] + \
                      [("saved/searches", a["name"]) for a in
                       json.loads((SPLUNK_DIR / "alerts.json").read_text())["alerts"]]:
        splunk.call("POST", f"/servicesNS/nobody/{APP}/{kind}/{urllib.parse.quote(name, safe='')}/acl",
                    {"sharing": "app", "owner": "nobody", "perms.read": "*", "perms.write": "admin"})


def search(splunk: Splunk, query: str, earliest: str) -> int:
    status, text = splunk.call("POST", "/services/search/jobs/export",
                               {"search": f"search {query}" if not query.lstrip().startswith("|") else query,
                                "earliest_time": earliest, "latest_time": "now"}, timeout=120)
    if status != 200:
        sys.exit(f"search: HTTP {status}: {text[:300]}")
    rows = [json.loads(line)["result"] for line in text.splitlines() if line.strip() and '"result"' in line]
    for row in rows:
        print(json.dumps({k: v for k, v in row.items() if not k.startswith("_") or k in ("_time", "_raw")}))
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-setup", action="store_true", help="also create the index and the HEC token")
    parser.add_argument("--wait", type=int, default=0, help="wait up to N seconds for the management API")
    parser.add_argument("--search", help="run this search and print the results instead of applying")
    parser.add_argument("--earliest", default="-60m")
    args = parser.parse_args()
    splunk = Splunk()
    if args.wait:
        splunk.wait_ready(args.wait)
    if args.search:
        sys.exit(0 if search(splunk, args.search, args.earliest) else 3)
    if args.local_setup:
        local_setup(splunk)
    apply_monitoring(splunk)


if __name__ == "__main__":
    main()
