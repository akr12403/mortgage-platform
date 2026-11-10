"""M9 Task 9.3: the Splunk dashboard, alerts and log shipping stay consistent with the log contract (stdlib only).

    python3 -m pytest tests/contract/test_splunk_assets.py
"""
import json
import re
import unittest
import xml.etree.ElementTree as ET  # parses our own committed dashboard file, not external input
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLUNK = ROOT / "monitoring" / "splunk"
RUNBOOK = ROOT / "docs" / "operations" / "runbook.md"
CONTRACT_FIELDS = {"message", "service.name", "log.level", "log.logger", "correlationId", "http.method",
                   "http.route", "http.status", "durationMs", "error.type"}
PAYMENT_ROUTE = 'http.route="/api/v1/mortgages/{id}/payments"'


def anchors(markdown: str) -> set[str]:
    return {re.sub(r"[^a-z0-9 -]", "", h.strip().lower()).replace(" ", "-")
            for h in re.findall(r"^#{1,6} (.+)$", markdown, flags=re.M)}


def dashboard_queries():
    root = ET.parse(SPLUNK / "dashboards" / "mortgage_platform_overview.xml").getroot()  # nosemgrep: python.lang.security.use-defused-xml-parse.use-defused-xml-parse -- repository file
    return [q.text for q in root.iter("query")]


class SplunkAssetsTest(unittest.TestCase):
    def test_every_search_uses_the_index_and_only_contract_fields(self):
        alerts = json.loads((SPLUNK / "alerts.json").read_text())["alerts"]
        searches = dashboard_queries() + [a["search"] for a in alerts]
        self.assertGreaterEqual(len(searches), 10)
        for search in searches:
            with self.subTest(search=search[:60]):
                self.assertIn("index=mortgage_dev", search)
                dotted = set(re.findall(r"\b((?:http|log|service|error)\.[a-z_]+)\b", search))
                self.assertLessEqual(dotted, CONTRACT_FIELDS, f"unknown fields {dotted - CONTRACT_FIELDS}")

    def test_payment_searches_use_the_route_template(self):
        payment = [s for s in dashboard_queries() if "payments" in s]
        payment += [a["search"] for a in json.loads((SPLUNK / "alerts.json").read_text())["alerts"]
                    if "Payment" in a["name"]]
        self.assertGreaterEqual(len(payment), 5)
        for search in payment:
            self.assertIn(PAYMENT_ROUTE, search)

    def test_alerts_have_runbook_sections_and_sane_settings(self):
        known = anchors(RUNBOOK.read_text())
        for alert in json.loads((SPLUNK / "alerts.json").read_text())["alerts"]:
            with self.subTest(alert=alert["name"]):
                self.assertTrue(alert["name"].startswith("mortgage_dev - "))
                path, _, anchor = alert["runbook"].partition("#")
                self.assertEqual(path, "docs/operations/runbook.md")
                self.assertIn(anchor, known, "runbook section missing")
                self.assertIn(alert["severity"], range(1, 7))
                self.assertRegex(alert["search"], r"\| where ")

    def test_log_shipping_takes_secrets_from_the_environment(self):
        compose = (ROOT / "docker-compose.splunk.yml").read_text()
        fluent = (SPLUNK / "fluent-bit" / "fluent-bit.conf").read_text()
        self.assertIn("${SPLUNK_HEC_TOKEN:?", compose)
        self.assertIn("Splunk_Token     ${SPLUNK_HEC_TOKEN}", fluent)
        self.assertNotRegex(compose + fluent, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                            "a literal HEC token (UUID) is committed")
        self.assertIn("Event_Sourcetype mortgage:app:json", fluent)
        self.assertIn("127.0.0.1:", compose, "local Splunk ports must stay on localhost")
        for service in ("mortgage-service", "servicing-service", "analytics-service", "knowledge-assistant"):
            self.assertRegex(compose, rf"\n  {service}: \*ship-logs")
        self.assertIn(".env.*", (ROOT / ".gitignore").read_text(), ".env.splunk-local must be git-ignored")


if __name__ == "__main__":
    unittest.main(verbosity=2)
