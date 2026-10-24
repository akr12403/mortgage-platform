"""M6 Task 6.2 RBAC smoke test against the RUNNING stack, using REAL logins for all five seed users.

    python3 tests/security/test_rbac_smoke.py

Only read endpoints are exercised for allowed roles; write endpoints are only exercised for roles that must be
DENIED, so running this never changes data.
"""
import unittest

from test_auth_smoke import MORTGAGE, SERVICING, call, seed_password

ANALYTICS = "http://localhost:8000"
USERS = {
    "ADMIN": "admin@capstone.local",
    "UNDERWRITER": "underwriter@capstone.local",
    "SERVICING_AGENT": "servicing@capstone.local",
    "RISK_ANALYST": "risk@capstone.local",
    "SUPPORT": "support@capstone.local",
}
VALID_MORTGAGE = {"mortgageExternalId": "MTG-0001", "borrowerExternalId": "BOR-001", "originalAmount": 1000.00,
                  "outstandingBalance": 1000.00, "originationDate": "2025-06-01"}
VALID_PAYMENT = {"dueDate": "2026-03-01", "paidDate": "2026-03-02", "amount": 1.00, "status": "POSTED"}

# (description, method, url, body, roles that must be ALLOWED). Writes list only roles we test as denied.
READS = [
    ("GET mortgage", "GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001", None, set(USERS)),
    ("GET payments", "GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001/payments", None, set(USERS)),
    ("GET borrower PII", "GET", f"{MORTGAGE}/api/v1/borrowers/BOR-001", None, {"ADMIN", "UNDERWRITER", "SERVICING_AGENT"}),
    ("GET servicing-history", "GET", f"{SERVICING}/api/v1/mortgages/MTG-1001/servicing-history", None, set(USERS)),
    ("GET delinquency", "GET", f"{SERVICING}/api/v1/mortgages/MTG-1002/delinquency", None, set(USERS)),
    ("GET analytics summary", "GET", f"{ANALYTICS}/api/v1/analytics/portfolio-summary", None, {"ADMIN", "UNDERWRITER", "RISK_ANALYST"}),
]
DENIED_WRITES = [
    ("POST mortgage", "POST", f"{MORTGAGE}/api/v1/mortgages", VALID_MORTGAGE, {"SERVICING_AGENT", "RISK_ANALYST", "SUPPORT"}),
    ("POST loan approval", "POST", f"{MORTGAGE}/api/v1/mortgages/MTG-1001/underwriting-decision", {"decision": "APPROVED"},
     {"SERVICING_AGENT", "RISK_ANALYST", "SUPPORT"}),
    ("POST payment", "POST", f"{MORTGAGE}/api/v1/mortgages/MTG-1001/payments", VALID_PAYMENT, {"UNDERWRITER", "RISK_ANALYST", "SUPPORT"}),
    ("POST delinquency evaluation", "POST", f"{MORTGAGE}/api/v1/delinquency-evaluations", None, {"UNDERWRITER", "RISK_ANALYST", "SUPPORT"}),
    ("POST servicing note", "POST", f"{SERVICING}/api/v1/mortgages/MTG-1001/servicing-events",
     {"eventType": "ESCROW_ANALYSIS"}, {"UNDERWRITER", "RISK_ANALYST", "SUPPORT"}),
]


class RbacSmokeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        password = seed_password()
        cls.tokens = {}
        for role, username in USERS.items():
            status, _, body = call("POST", f"{MORTGAGE}/api/v1/auth/login", {"username": username, "password": password})
            assert status == 200, f"login failed for {username}: {status} {body}"
            assert body["roles"] == [role], body
            cls.tokens[role] = body["accessToken"]

    def test_reads_follow_matrix_for_all_five_roles(self):
        for name, method, url, body, allowed in READS:
            for role, token in self.tokens.items():
                with self.subTest(endpoint=name, role=role):
                    status, _, response = call(method, url, body, token)
                    if role in allowed:
                        self.assertEqual(status, 200, response)
                    else:
                        self.assertEqual(status, 403, response)
                        self.assertEqual(response["code"], "ACCESS_DENIED")

    def test_writes_are_denied_for_unauthorized_roles(self):
        for name, method, url, body, denied in DENIED_WRITES:
            for role in denied:
                with self.subTest(endpoint=name, role=role):
                    status, _, response = call(method, url, body, self.tokens[role])
                    self.assertEqual(status, 403, response)
                    self.assertEqual(response["code"], "ACCESS_DENIED")

    def test_support_cannot_approve_loan_m10_journey4(self):
        status, _, response = call("POST", f"{MORTGAGE}/api/v1/mortgages/MTG-1001/underwriting-decision",
                                   {"decision": "APPROVED"}, self.tokens["SUPPORT"])
        self.assertEqual(status, 403)
        self.assertEqual(response["code"], "ACCESS_DENIED")

    def test_risk_analyst_sees_no_borrower_names_dp_gap_1(self):
        """M6 Task 6.6, DP-GAP-1: risk summary keeps the aggregates but drops names for RISK_ANALYST."""
        url = f"{ANALYTICS}/api/v1/analytics/borrowers/BOR-001/risk-summary"
        status, _, admin_view = call("GET", url, token=self.tokens["ADMIN"])
        self.assertEqual(status, 200, admin_view)
        self.assertIn("firstName", admin_view)
        status, _, risk_view = call("GET", url, token=self.tokens["RISK_ANALYST"])
        self.assertEqual(status, 200, risk_view)
        self.assertNotIn("firstName", risk_view)
        self.assertNotIn("lastName", risk_view)
        self.assertEqual(risk_view["borrowerExternalId"], "BOR-001")
        self.assertEqual(risk_view["totalOutstandingBalance"], admin_view["totalOutstandingBalance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
