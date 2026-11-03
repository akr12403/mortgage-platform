"""M8 Tasks 8.1/8.2: static least-privilege guard for the IAM and S3 policies in infrastructure/aws/.

    python3 tests/security/test_iam_policies.py      # stdlib only, no AWS account needed (runs in the sast CI job)

Fails if a policy grants a wildcard action (`*`, `service:*`), uses NotAction/NotResource, targets Resource `*`
or another account/Region wildcard, if a trust policy trusts anyone (`*`) or an unexpected service, or if a
role in roles.json is missing from docs/architecture/aws-iam-matrix.md. The over-permissioned exercise file
must be flagged, which proves the guard actually catches what it claims to.
"""
import json
import re
import string
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IAM = ROOT / "infrastructure" / "aws" / "iam"
RESOURCES_ENV = ROOT / "infrastructure" / "aws" / "resources.conf"
MATRIX = ROOT / "docs" / "architecture" / "aws-iam-matrix.md"
EXERCISE = IAM / "exercise" / "lambda-doc-processor-overpermissioned.json"

DERIVED = {"ACCOUNT_ID": "111122223333", "REGION": "us-east-2", "BUCKET": "capstone-mortgage-docs-dev",
           "DEV_PRINCIPAL_ARN": "arn:aws:iam::111122223333:role/AccountFullAccessRole"}
S3_DIR = ROOT / "infrastructure" / "aws" / "s3"
ALLOWED_SERVICE_PRINCIPALS = {"lambda.amazonaws.com", "glue.amazonaws.com"}


def _resources_env():
    values = {}
    for line in RESOURCES_ENV.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def _render(path):
    text = path.read_text()
    variables = {**_resources_env(), **DERIVED}
    doc = json.loads(string.Template(text).substitute(variables))  # unknown ${VAR} -> KeyError
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _as_list(value):
    return value if isinstance(value, list) else [value]


def policy_violations(doc):
    found = []
    if doc.get("Version") != "2012-10-17":
        found.append("Version must be 2012-10-17")
    for st in doc["Statement"]:
        sid = st.get("Sid", "?")
        if not st.get("Sid"):
            found.append("statement without Sid")
        for key in ("NotAction", "NotResource", "NotPrincipal"):
            if key in st:
                found.append(f"{sid}: {key} is not allowed")
        if st.get("Effect") != "Allow":
            continue
        for action in _as_list(st.get("Action", [])):
            if action == "*" or action.endswith(":*") or "*" in action:
                found.append(f"{sid}: wildcard action {action}")
            if action.lower() == "iam:passrole":
                found.append(f"{sid}: iam:PassRole is not needed by any service role")
        for resource in _as_list(st.get("Resource", [])):
            if resource == "*":
                found.append(f"{sid}: Resource *")
                continue
            parts = resource.split(":", 5)
            if len(parts) < 6:
                found.append(f"{sid}: not an ARN: {resource}")
                continue
            _, _, service, region, account, rest = parts
            if service != "s3" and (region in ("", "*") or account in ("", "*")):
                found.append(f"{sid}: Region/account wildcard in {resource}")
            if service == "s3" and rest.split("/", 1)[0] in ("", "*"):
                found.append(f"{sid}: bucket wildcard in {resource}")
            if rest.endswith(":*") and service not in ("logs",) or rest in ("table/*", "*"):
                found.append(f"{sid}: unscoped resource {resource}")
    return found


def trust_violations(doc):
    found = []
    for st in doc["Statement"]:
        if st.get("Action") != "sts:AssumeRole":
            found.append(f"{st.get('Sid')}: trust action must be exactly sts:AssumeRole")
        principal = st.get("Principal")
        if principal == "*" or not isinstance(principal, dict):
            found.append(f"{st.get('Sid')}: principal must be a specific role or service")
            continue
        for kind, values in principal.items():
            for value in _as_list(values):
                if "*" in value:
                    found.append(f"{st.get('Sid')}: wildcard principal {value}")
                if kind == "Service" and value not in ALLOWED_SERVICE_PRINCIPALS:
                    found.append(f"{st.get('Sid')}: unexpected service principal {value}")
                if kind == "AWS" and not value.startswith("arn:aws:iam::"):
                    found.append(f"{st.get('Sid')}: AWS principal must be a role ARN")
    return found


ROLES = json.loads((IAM / "roles.json").read_text())["roles"]


class IamPolicyTests(unittest.TestCase):
    def test_manifest_lists_the_three_required_roles(self):
        names = {r["name"] for r in ROLES}
        self.assertTrue({"mortgage-analytics-role", "mortgage-api-role", "lambda-doc-processor-role"} <= names)

    def test_every_role_policy_is_least_privilege(self):
        for role in ROLES:
            with self.subTest(role=role["name"]):
                self.assertEqual(policy_violations(_render(IAM / role["policy"])), [])

    def test_every_trust_policy_names_a_specific_principal(self):
        for role in ROLES:
            with self.subTest(role=role["name"]):
                self.assertEqual(trust_violations(_render(IAM / role["trust"])), [])

    def test_no_policy_file_is_left_out_of_the_manifest(self):
        used = {r["policy"] for r in ROLES} | {r["trust"] for r in ROLES}
        on_disk = {str(p.relative_to(IAM)) for p in list((IAM / "policies").glob("*.json"))
                   + list((IAM / "trust").glob("*.json"))}
        self.assertEqual(on_disk - used, set())

    def test_overpermissioned_exercise_is_caught(self):
        found = policy_violations(_render(EXERCISE))
        joined = "\n".join(found)
        for expected in ("wildcard action s3:*", "Resource *", "wildcard action dynamodb:*", "iam:PassRole"):
            self.assertIn(expected, joined)

    def test_matrix_documents_every_role(self):
        matrix = MATRIX.read_text()
        for role in ROLES:
            with self.subTest(role=role["name"]):
                self.assertIn(f"`{role['name']}`", matrix)

    def test_bucket_policy_only_denies_the_public_and_requires_tls(self):
        doc = _render(S3_DIR / "bucket-policy.json")
        for st in doc["Statement"]:
            with self.subTest(sid=st.get("Sid")):
                if st.get("Principal") == "*" or st.get("Principal") == {"AWS": "*"}:
                    self.assertEqual(st["Effect"], "Deny", "a public principal may only appear in a Deny")
                self.assertNotIn("NotPrincipal", st)
        tls = next(st for st in doc["Statement"] if st["Sid"] == "DenyInsecureTransport")
        self.assertEqual(tls["Condition"], {"Bool": {"aws:SecureTransport": "false"}})
        self.assertEqual(set(tls["Resource"]), {"arn:aws:s3:::capstone-mortgage-docs-dev",
                                                "arn:aws:s3:::capstone-mortgage-docs-dev/*"})

    def test_lifecycle_rules_are_scoped_and_bounded(self):
        for path in sorted(S3_DIR.glob("lifecycle-*.json")):
            with self.subTest(file=path.name):
                rules = _render(path)["Rules"]
                self.assertTrue(any("AbortIncompleteMultipartUpload" in r for r in rules))
                for rule in rules:
                    if "Expiration" in rule:
                        self.assertTrue(rule["Filter"].get("Prefix"), "expiration must be limited to a prefix")
                        self.assertGreaterEqual(rule["Expiration"]["Days"], 7)

    def test_no_account_id_or_keys_committed(self):
        for path in (ROOT / "infrastructure" / "aws").rglob("*"):
            if path.is_file():
                text = path.read_text()
                with self.subTest(file=str(path.relative_to(ROOT))):
                    self.assertIsNone(re.search(r"(?<![\d.])\d{12}(?![\d.])", text), "hard-coded account id")
                    self.assertIsNone(re.search(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b", text), "access key id")


if __name__ == "__main__":
    unittest.main(verbosity=2)
