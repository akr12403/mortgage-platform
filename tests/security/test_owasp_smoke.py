"""M6 Task 6.3 smoke test against the RUNNING compose stack (stdlib only).

    python3 tests/security/test_owasp_smoke.py

Live checks for the OWASP API Top 10 controls: security headers on all three services, mass-assignment fix,
injection probes, input validation, bounded pagination, login throttling (uses a random throwaway username, so
it never locks out the seed users used by the other smoke tests and the demo).
"""
import json
import unittest
import urllib.error
import urllib.request
import uuid

from test_auth_smoke import MORTGAGE, SERVICING, call, seed_password

ANALYTICS = "http://localhost:8000"


def raw(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as err:
        with err:
            return err.code, err.headers, err.read()


def login(username):
    status, _, body = call("POST", f"{MORTGAGE}/api/v1/auth/login", {"username": username, "password": seed_password()})
    assert status == 200, f"login {username}: {status} {body}"
    return body["accessToken"]


class OwaspSmokeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.admin = login("admin@capstone.local")
        cls.agent = login("servicing@capstone.local")

    def auth(self, token=None):
        return {"Authorization": f"Bearer {token or self.admin}"}

    # API8 security misconfiguration
    def test_security_headers_on_all_services(self):
        for url in (f"{MORTGAGE}/api/v1/mortgages/MTG-1001", f"{SERVICING}/api/v1/mortgages/MTG-1001/servicing-history",
                    f"{ANALYTICS}/api/v1/analytics/portfolio-summary"):
            status, headers, _ = raw("GET", url, headers=self.auth())
            self.assertEqual(status, 200, url)
            self.assertIn("default-src 'none'", headers.get("Content-Security-Policy", ""), url)
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff", url)
            self.assertEqual(headers.get("X-Frame-Options"), "DENY", url)
            self.assertIn("Permissions-Policy", headers, url)
            self.assertIn("no-store", headers.get("Cache-Control", ""), url)

    def test_errors_do_not_leak_stack_traces(self):
        status, _, body = raw("POST", f"{MORTGAGE}/api/v1/mortgages", b"{not json",
                              {**self.auth(), "Content-Type": "application/json"})
        self.assertEqual(status, 400)
        payload = json.loads(body)
        self.assertEqual(payload["code"], "VALIDATION_ERROR")
        self.assertIn("correlationId", payload)
        for leak in (b"Exception", b"at com.", b"jackson", b"trace"):
            self.assertNotIn(leak, body)

    # Injection
    def test_sql_injection_probes_are_plain_values(self):
        for probe in ("MTG-1001'%20OR%20'1'='1", "MTG-1001%27%20UNION%20SELECT%20password_hash%20FROM%20app_user--"):
            status, _, body = raw("GET", f"{MORTGAGE}/api/v1/mortgages/{probe}", headers=self.auth())
            self.assertEqual(status, 404, probe)
            self.assertEqual(json.loads(body)["code"], "MORTGAGE_NOT_FOUND")
        status, _, _ = raw("GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001", headers=self.auth())
        self.assertEqual(status, 200, "mortgage table still intact")
        status, _, body = raw("GET", f"{ANALYTICS}/api/v1/analytics/borrowers/BOR-001'%20OR%20'1'='1/risk-summary",
                              headers=self.auth())
        self.assertEqual(status, 400)

    # API4 unrestricted resource consumption
    def test_page_size_is_bounded(self):
        status, _, body = call("GET", f"{MORTGAGE}/api/v1/mortgages?borrowerId=BOR-001&size=100000", token=self.admin)
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    def test_payment_trends_range_is_bounded(self):
        status, _, body = raw("GET", f"{ANALYTICS}/api/v1/analytics/payment-trends?from=1900-01-01&to=2026-01-01",
                              headers=self.auth())
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["code"], "VALIDATION_ERROR")

    def test_login_is_rate_limited(self):
        throwaway = f"ratelimit-{uuid.uuid4().hex[:8]}@capstone.local"
        statuses = []
        for _ in range(11):
            status, headers, body = call("POST", f"{MORTGAGE}/api/v1/auth/login",
                                         {"username": throwaway, "password": "definitely-wrong-1"})
            statuses.append(status)
        self.assertEqual(statuses[:10], [401] * 10)
        self.assertEqual(statuses[10], 429)
        self.assertEqual(body["code"], "RATE_LIMITED")
        self.assertGreaterEqual(int(headers["Retry-After"]), 1)

    # API3 broken object property level authorization (VULN-M6-001)
    def test_payment_body_cannot_choose_the_payment_id(self):
        status, _, payments = call("GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001/payments", token=self.agent)
        self.assertEqual(status, 200)
        if not payments:
            self.skipTest("MTG-1001 has no payments to target")
        victim = payments[0]
        key = f"owasp-{uuid.uuid4()}"
        body = {"id": victim["id"], "dueDate": "2026-03-01", "paidDate": "2026-03-01", "amount": 0.01, "status": "POSTED"}
        req = urllib.request.Request(f"{MORTGAGE}/api/v1/mortgages/MTG-1001/payments", method="POST",
                                     data=json.dumps(body).encode(),
                                     headers={**self.auth(self.agent), "Content-Type": "application/json",
                                              "Idempotency-Key": key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            created = json.loads(resp.read())
        self.assertNotEqual(created["id"], victim["id"], "client-supplied id must be ignored")
        _, _, after = call("GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001/payments", token=self.agent)
        unchanged = next(p for p in after if p["id"] == victim["id"])
        self.assertEqual(unchanged["amount"], victim["amount"])
        self.assertEqual(unchanged["status"], victim["status"])

    def test_document_upload_rejects_executables(self):
        boundary = "owaspboundary"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="mortgage_external_id"\r\n\r\nMTG-1001\r\n',
            f'--{boundary}\r\nContent-Disposition: form-data; name="document_type"\r\n\r\nDEED\r\n',
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="evil.exe"\r\n'
            f'Content-Type: application/x-msdownload\r\n\r\nMZ\x90\r\n',
            f'--{boundary}--\r\n',
        ]
        status, _, body = raw("POST", f"{ANALYTICS}/api/v1/documents/upload", "".join(parts).encode("latin-1"),
                              {**self.auth(), "Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(status, 415, body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
