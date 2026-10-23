"""M6 Task 6.1 smoke test against the RUNNING compose stack (stdlib only, no pip install needed).

    python3 tests/security/test_auth_smoke.py

Reads AUTH_SEED_PASSWORD from the environment or the repo-root .env. Checks: login works and returns the
required claims; missing / tampered / wrong-password cases get 401 with the error envelope; health stays public;
the token is accepted by BOTH Java services.
"""
import base64
import json
import os
import unittest
import urllib.error
import urllib.request
from pathlib import Path

MORTGAGE = os.getenv("MORTGAGE_API_BASE", "http://localhost:8080")
SERVICING = os.getenv("SERVICING_API_BASE", "http://localhost:8081")


def seed_password():
    if os.getenv("AUTH_SEED_PASSWORD"):
        return os.environ["AUTH_SEED_PASSWORD"]
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("AUTH_SEED_PASSWORD=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip()
    raise unittest.SkipTest("AUTH_SEED_PASSWORD is empty/not set: fill it in .env, then restart the stack")


def call(method, url, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), json.loads(err.read() or b"{}")


def claims(token):
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


class AuthSmokeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        status, _, body = call("POST", f"{MORTGAGE}/api/v1/auth/login",
                               {"username": "servicing@capstone.local", "password": seed_password()})
        assert status == 200, f"login failed: {status} {body}"
        cls.login = body

    def test_login_contract_and_claims(self):
        self.assertEqual(self.login["tokenType"], "Bearer")
        self.assertEqual(self.login["roles"], ["SERVICING_AGENT"])
        c = claims(self.login["accessToken"])
        self.assertEqual(c["sub"], "servicing@capstone.local")
        self.assertEqual(c["roles"], ["SERVICING_AGENT"])
        self.assertEqual(c["iss"], "capstone-mortgage-auth")
        self.assertGreater(c["exp"], c["iat"])

    def test_token_accepted_by_both_services(self):
        token = self.login["accessToken"]
        self.assertEqual(call("GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001", token=token)[0], 200)
        self.assertEqual(call("GET", f"{SERVICING}/api/v1/mortgages/MTG-1001/servicing-history", token=token)[0], 200)

    def test_missing_token_is_401_with_envelope(self):
        for url in (f"{MORTGAGE}/api/v1/mortgages/MTG-1001", f"{SERVICING}/api/v1/mortgages/MTG-1001/delinquency"):
            status, _, body = call("GET", url)
            self.assertEqual(status, 401, url)
            self.assertEqual(body["code"], "UNAUTHORIZED")
            self.assertIn("correlationId", body)

    def test_tampered_token_is_401(self):
        header, _, signature = self.login["accessToken"].split(".")
        forged = base64.urlsafe_b64encode(json.dumps(
            {"sub": "attacker", "roles": ["ADMIN"], "iss": "capstone-mortgage-auth", "exp": 4102444800}
        ).encode()).decode().rstrip("=")
        status, _, body = call("GET", f"{MORTGAGE}/api/v1/mortgages/MTG-1001", token=f"{header}.{forged}.{signature}")
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "INVALID_TOKEN")

    def test_wrong_password_is_401_without_hinting(self):
        status, _, body = call("POST", f"{MORTGAGE}/api/v1/auth/login",
                               {"username": "servicing@capstone.local", "password": "definitely-wrong"})
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "INVALID_CREDENTIALS")
        _, _, unknown = call("POST", f"{MORTGAGE}/api/v1/auth/login",
                             {"username": "nobody@capstone.local", "password": "definitely-wrong"})
        self.assertEqual(unknown["message"], body["message"])

    def test_mutation_without_token_is_401(self):
        status, _, _ = call("POST", f"{MORTGAGE}/api/v1/mortgages", {"mortgageExternalId": "MTG-0001"})
        self.assertEqual(status, 401)

    def test_health_is_public(self):
        self.assertEqual(call("GET", f"{MORTGAGE}/actuator/health")[0], 200)
        self.assertEqual(call("GET", f"{SERVICING}/actuator/health")[0], 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
