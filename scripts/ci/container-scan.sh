#!/usr/bin/env bash
# M9 Task 9.1: container image scan with Trivy (policy: docs/operations/cicd.md#container-scan-policy).
#   bash scripts/ci/container-scan.sh <image-ref> <service>
#   bash scripts/ci/container-scan.sh capstone/mortgage-service:dev mortgage-service     # local image works too
# Gate: FAIL on any CRITICAL vulnerability that has a fixed version (OS packages and language libraries in the image).
# Report: every HIGH and CRITICAL (fixed or not) in reports/security/trivy-image-<service>.txt, plus JSON for tooling.
# Accepted exceptions: .trivyignore (each entry has a reason and an exp: date, after which the gate fails again).
# Registry credentials (CI): TRIVY_USERNAME / TRIVY_PASSWORD in the environment; never on the command line.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
image="${1:?usage: container-scan.sh <image-ref> <service>}"
service="${2:?usage: container-scan.sh <image-ref> <service>}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.75.0}"
OUT="reports/security"; mkdir -p "$OUT" reports/.cache/trivy

trivy() {
  docker run --rm \
    -e TRIVY_USERNAME -e TRIVY_PASSWORD \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$ROOT":/src -w /src \
    -v "$ROOT/reports/.cache/trivy":/root/.cache/trivy \
    "$TRIVY_IMAGE" "$@"
}

printf '\n\033[1;36m== Container scan: %s ==\033[0m\n' "$image"
# 1. Full report (HIGH + CRITICAL, including unfixed) - never fails the job.
trivy image --quiet --scanners vuln --severity HIGH,CRITICAL --ignorefile .trivyignore \
  --format table --output "$OUT/trivy-image-$service.txt" "$image"
trivy image --quiet --scanners vuln --severity HIGH,CRITICAL --ignorefile .trivyignore \
  --format json --output "$OUT/trivy-image-$service.json" "$image"

# 2. Gate: CRITICAL with a fix available.
rc=0
trivy image --quiet --scanners vuln --severity CRITICAL --ignore-unfixed --ignorefile .trivyignore \
  --exit-code 1 --format table "$image" || rc=$?

python3 - "$OUT/trivy-image-$service.json" "$service" "$rc" <<'PY' >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
import json, sys
path, service, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
counts = {("CRITICAL", True): 0, ("CRITICAL", False): 0, ("HIGH", True): 0, ("HIGH", False): 0}
for result in json.load(open(path)).get("Results") or []:
    for v in result.get("Vulnerabilities") or []:
        key = (v["Severity"], bool(v.get("FixedVersion")))
        counts[key] = counts.get(key, 0) + 1
print(f"### Container scan: `{service}` - {'PASS' if rc == 0 else 'FAIL'}\n")
print("| Severity | fix available | no fix yet |\n| --- | --- | --- |")
for sev in ("CRITICAL", "HIGH"):
    print(f"| {sev} | {counts[(sev, True)]} | {counts[(sev, False)]} |")
print("\nGate: CRITICAL with a fix available fails the pipeline. Full list: artifact `container-scan-" + service + "`.\n")
PY

if [ "$rc" -eq 0 ]; then
  printf '\033[1;32mPASS\033[0m no fixable CRITICAL vulnerabilities in %s (report: %s)\n' "$image" "$OUT/trivy-image-$service.txt"
else
  printf '\033[1;31mFAIL\033[0m fixable CRITICAL vulnerabilities in %s: rebuild on a patched base image or bump the library (see above)\n' "$image"
fi
exit "$rc"
