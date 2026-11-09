"""M9 Task 9.2 static guard for infrastructure/terraform (stdlib only; no Terraform or AWS needed, runs in CI).

    python3 tests/infrastructure/test_terraform_layout.py

Checks the things `terraform validate` can't:
- the handbook layout (5 modules, dev/test/prod) and that every module has main/variables/outputs;
- environments differ only in tfvars/backend (main.tf, variables.tf, outputs.tf, versions.tf identical);
- remote state: S3 backend with native locking + encryption, one key per environment, no bucket/account committed;
- dev resource names equal the M8 names in infrastructure/aws/resources.conf (so imports.tf adopts, not recreates);
- no account ids, access keys, secrets or personal IPs committed (0.0.0.0/0 ingress is rejected by a variable
  validation in modules/security); imports only in dev;
- every variable has a description and a type.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TF = ROOT / "infrastructure" / "terraform"
ENVS = ("dev", "test", "prod")
MODULES = ("networking", "security", "storage", "compute", "messaging")
SHARED_ENV_FILES = ("main.tf", "variables.tf", "outputs.tf", "versions.tf")


def tf_files():
    return sorted(p for p in TF.rglob("*") if p.suffix in (".tf", ".tfvars") and ".terraform" not in p.parts)


def resources_conf():
    conf = {}
    for line in (ROOT / "infrastructure" / "aws" / "resources.conf").read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


class TerraformLayoutTest(unittest.TestCase):
    def test_handbook_layout(self):
        for m in MODULES:
            for f in ("main.tf", "variables.tf", "outputs.tf"):
                with self.subTest(module=m, file=f):
                    self.assertTrue((TF / "modules" / m / f).is_file())
        for e in ENVS:
            for f in SHARED_ENV_FILES + ("backend.tf", "terraform.tfvars"):
                with self.subTest(env=e, file=f):
                    self.assertTrue((TF / "environments" / e / f).is_file())
        self.assertTrue((TF / "bootstrap" / "main.tf").is_file())

    def test_environments_share_one_definition(self):
        for f in SHARED_ENV_FILES:
            dev = (TF / "environments" / "dev" / f).read_text()
            for e in ("test", "prod"):
                with self.subTest(file=f, env=e):
                    self.assertEqual((TF / "environments" / e / f).read_text(), dev,
                                     f"environments/{e}/{f} differs from dev: put differences in terraform.tfvars")

    def test_remote_state_backend(self):
        keys = set()
        for e in ENVS:
            text = (TF / "environments" / e / "backend.tf").read_text()
            with self.subTest(env=e):
                self.assertIn('backend "s3"', text)
                self.assertRegex(text, r"use_lockfile\s*=\s*true")
                self.assertRegex(text, r"encrypt\s*=\s*true")
                self.assertNotRegex(text, r"^\s*bucket\s*=", "bucket is passed at init (contains the account id)")
                self.assertNotIn("dynamodb_table", text)
                key = re.search(r'key\s*=\s*"([^"]+)"', text).group(1)
                self.assertIn(f"/{e}/", key)
                keys.add(key)
        self.assertEqual(len(keys), len(ENVS), "each environment needs its own state key")

    def test_dev_names_match_m8_resources(self):
        conf = resources_conf()
        main = (TF / "environments" / "dev" / "main.tf").read_text()
        names = dict(re.findall(r'^\s+([A-Z_]+)\s*=\s*"([^"]*\$\{local\.env\}[^"]*)"', main, flags=re.M))
        prefixes = dict(re.findall(r'^\s+([A-Z_]+_PREFIX)\s*=\s*"([^"]+)"', main, flags=re.M))
        self.assertGreaterEqual(len(names), 10)
        for key, template in names.items():
            with self.subTest(name=key):
                self.assertEqual(template.replace("${local.env}", "dev"), conf[key])
        for key, value in prefixes.items():
            with self.subTest(prefix=key):
                self.assertEqual(value, conf[key])
        self.assertIn('default     = "us-east-2"', (TF / "environments" / "dev" / "variables.tf").read_text())

    def test_imports_only_in_dev(self):
        self.assertTrue((TF / "environments" / "dev" / "imports.tf").is_file())
        for e in ("test", "prod"):
            self.assertFalse((TF / "environments" / e / "imports.tf").exists())
        for p in tf_files():
            if p.name != "imports.tf":
                with self.subTest(file=str(p.relative_to(ROOT))):
                    self.assertNotRegex(p.read_text(), r"^\s*import\s*\{", "import blocks belong in dev/imports.tf")

    def test_nothing_sensitive_committed(self):
        patterns = {
            "account id": r"(?<![0-9.])\d{12}(?![0-9])",
            "access key": r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
            "static credentials": r"\b(access_key|secret_key|token)\s*=",
            "hard-coded password": r"(?i)\bpassword\s*=\s*\"[^\"]+\"",
        }
        for p in tf_files():
            text = p.read_text()
            for label, pattern in patterns.items():
                with self.subTest(file=str(p.relative_to(ROOT)), check=label):
                    self.assertIsNone(re.search(pattern, text), f"{label} in {p.name}")
        for e in ENVS:
            tfvars = (TF / "environments" / e / "terraform.tfvars").read_text()
            with self.subTest(env=e):
                self.assertNotIn("allowed_ingress_cidrs", tfvars, "pass your IP with -var, don't commit it")
                self.assertNotIn("developer_principal_arn", tfvars, "contains the account id")
        self.assertNotRegex((TF / "environments" / "prod" / "terraform.tfvars").read_text(),
                            r"sandbox_teardown\s*=\s*true")

    def test_every_variable_is_documented_and_typed(self):
        for p in tf_files():
            for block in re.findall(r'variable\s+"[^"]+"\s*\{(.*?)\n\}', p.read_text(), flags=re.S):
                with self.subTest(file=str(p.relative_to(ROOT)), variable=block[:40]):
                    self.assertRegex(block, r"\bdescription\s*=")
                    self.assertRegex(block, r"\btype\s*=")

    def test_terraform_state_and_build_output_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text()
        for entry in (".terraform/", "*.tfstate", "*.tfstate.*", "*.tfplan", ".build/"):
            with self.subTest(entry=entry):
                self.assertIn(entry, ignore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
