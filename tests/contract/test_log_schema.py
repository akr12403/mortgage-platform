"""M9 Task 9.3: every service emits the same structured log contract (docs/operations/observability.md).

    python3 -m pytest tests/contract/test_log_schema.py      # stdlib only; also runs in CI (repo-checks)

Static checks that keep the four services aligned; the behaviour itself is tested in each service
(RequestLoggingTest in both Java services, tests/test_structured_logging.py in both Python services).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY_SERVICES = {
    "mortgage-analytics-service": ROOT / "analytics" / "mortgage-analytics-service",
    "mortgage-knowledge-assistant": ROOT / "ai" / "mortgage-knowledge-assistant",
}
JAVA_SERVICES = {
    "mortgage-service": ROOT / "services" / "mortgage-service",
    "servicing-service": ROOT / "services" / "servicing-service",
}
CONTRACT_FIELDS = ("@timestamp", "log.level", "service.name", "log.logger", "message", "correlationId",
                   "http.method", "http.route", "http.status", "durationMs")


class LogSchemaTest(unittest.TestCase):
    def test_python_services_share_one_logging_module(self):
        copies = {name: (path / "src" / "observability.py").read_text() for name, path in PY_SERVICES.items()}
        first, second = copies.values()
        self.assertEqual(first, second, "keep both copies of src/observability.py identical")
        for field in CONTRACT_FIELDS:
            self.assertIn(f'"{field}"', first, f"observability.py does not write {field}")

    def test_python_services_use_it(self):
        for name, path in PY_SERVICES.items():
            main = (path / "src" / "api" / "main.py").read_text()
            with self.subTest(service=name):
                self.assertIn(f'configure_logging(', main)
                self.assertIn("log_http_request(", main)
                self.assertIn("correlation_id_var.set(", main)
                self.assertNotIn("logging.basicConfig(", main, "plain-text logging would bypass the JSON formatter")

    def test_java_services_log_ecs_json_and_one_line_per_request(self):
        for name, path in JAVA_SERVICES.items():
            logback = (path / "src" / "main" / "resources" / "logback-spring.xml").read_text()
            app_yml = (path / "src" / "main" / "resources" / "application.yml").read_text()
            filters = list((path / "src" / "main" / "java").rglob("RequestLoggingFilter.java"))
            with self.subTest(service=name):
                self.assertIn("StructuredLogEncoder", logback)
                self.assertRegex(logback, r"<format>\s*ecs\s*</format>")
                self.assertNotIn("<pattern>", logback, "a text pattern would bypass the JSON encoder")
                self.assertRegex(app_yml, rf"name:\s*{re.escape(name)}\b", "service.name comes from spring.application.name")
                self.assertEqual(len(filters), 1)
                source = filters[0].read_text()
                for field in ("http.method", "http.route", "http.status", "durationMs"):
                    self.assertIn(f'"{field}"', source)
                self.assertIn("BEST_MATCHING_PATTERN_ATTRIBUTE", source, "log the route template, not the raw path")

    def test_contract_is_documented(self):
        doc = (ROOT / "docs" / "operations" / "observability.md").read_text()
        for field in CONTRACT_FIELDS:
            self.assertIn(f"`{field}`", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
