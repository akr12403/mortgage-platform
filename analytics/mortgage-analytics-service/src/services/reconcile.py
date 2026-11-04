"""M8 Task 8.6: reconcile PostgreSQL (system of record) against the curated delinquency report.

    python -m src.services.reconcile [--date YYYY-MM-DD]     # scripts/aws/reconcile.sh runs it as mortgage-analytics-role

Checks (tolerances documented in docs/operations/data-pipeline-runbook.md#reconciliation):
  ROW_COUNT          PostgreSQL mortgages vs curated rows                    0 difference           FAIL
  BALANCE_SUM        sum(outstanding_balance) PostgreSQL vs curated          |diff| <= 0.01          FAIL
  KEY_SET            mortgage IDs missing from / extra in curated            none                   FAIL
  ROW_BALANCE        per-mortgage balance difference                         |diff| <= 0.01 each     FAIL
  DELINQUENT_COUNT   delinquency records vs curated is_delinquent=true       0 difference           FAIL
  MANIFEST           curated _manifest.json rowCount vs file rows            equal                  FAIL
  EXPORT_CONTROL     curated vs the export's own control totals (raw zone)   rows 0, balance 0.01   FAIL
  DQ_SEVERITY_BAND   severity matches days past due (30-59 MODERATE,         informational          WARN
                     60-89 SEVERE, 90+ CRITICAL; delinquency playbook)

Result: PASS when no check FAILs (WARNs are reported but do not fail). Exit code 0 PASS, 1 FAIL, 2 cannot run.
Reconcile right after a pipeline run: PostgreSQL changes after the export show up as differences (by design).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

BALANCE_TOLERANCE = Decimal("0.01")
ROW_TOLERANCE = 0
SEVERITY_BANDS = ((90, "CRITICAL"), (60, "SEVERE"), (30, "MODERATE"))


def expected_severity(days_past_due: int):
    for floor, severity in SEVERITY_BANDS:
        if days_past_due >= floor:
            return severity
    return None


def _check(name, status, expected, actual, detail="", tolerance=None):
    out = {"check": name, "status": status, "expected": expected, "actual": actual}
    if tolerance is not None:
        out["tolerance"] = tolerance
    if detail:
        out["detail"] = detail
    return out


def reconcile(pg_rows: list, pg_delinquent_count: int, curated_rows: list, manifest: dict,
              export_manifest: dict | None = None) -> dict:
    """pg_rows: [{mortgage_external_id, outstanding_balance}]; curated_rows: rows of part-0000.csv."""
    checks = []
    pg_balance = {r["mortgage_external_id"]: Decimal(str(r["outstanding_balance"])) for r in pg_rows}
    cur_balance = {r["mortgage_external_id"]: Decimal(r["outstanding_balance"]) for r in curated_rows}

    diff_rows = len(curated_rows) - len(pg_rows)
    checks.append(_check("ROW_COUNT", "PASS" if abs(diff_rows) <= ROW_TOLERANCE else "FAIL",
                         len(pg_rows), len(curated_rows), f"difference {diff_rows:+d}", ROW_TOLERANCE))

    pg_sum, cur_sum = sum(pg_balance.values(), Decimal("0")), sum(cur_balance.values(), Decimal("0"))
    diff_sum = cur_sum - pg_sum
    checks.append(_check("BALANCE_SUM", "PASS" if abs(diff_sum) <= BALANCE_TOLERANCE else "FAIL",
                         str(pg_sum), str(cur_sum), f"difference {diff_sum:+.2f}", str(BALANCE_TOLERANCE)))

    missing, extra = sorted(set(pg_balance) - set(cur_balance)), sorted(set(cur_balance) - set(pg_balance))
    checks.append(_check("KEY_SET", "PASS" if not (missing or extra) else "FAIL", "same mortgage IDs",
                         {"missingFromCurated": missing[:10], "extraInCurated": extra[:10]},
                         f"{len(missing)} missing, {len(extra)} extra"))

    mismatched = [{"mortgageExternalId": k, "postgres": str(pg_balance[k]), "curated": str(cur_balance[k])}
                  for k in sorted(set(pg_balance) & set(cur_balance))
                  if abs(pg_balance[k] - cur_balance[k]) > BALANCE_TOLERANCE]
    checks.append(_check("ROW_BALANCE", "PASS" if not mismatched else "FAIL", "each within 0.01",
                         mismatched[:10], f"{len(mismatched)} mortgage(s) differ", str(BALANCE_TOLERANCE)))

    cur_delinquent = sum(1 for r in curated_rows if r["is_delinquent"] == "true")
    checks.append(_check("DELINQUENT_COUNT", "PASS" if cur_delinquent == pg_delinquent_count else "FAIL",
                         pg_delinquent_count, cur_delinquent, tolerance=0))

    checks.append(_check("MANIFEST", "PASS" if manifest.get("rowCount") == len(curated_rows) else "FAIL",
                         manifest.get("rowCount"), len(curated_rows), "curated _manifest.json rowCount vs file rows"))

    if export_manifest:
        exp_rows = export_manifest["rowCounts"]["mortgage"]
        exp_sum = Decimal(str(export_manifest["mortgageOutstandingBalanceTotal"]))
        ok = exp_rows == len(curated_rows) and abs(exp_sum - cur_sum) <= BALANCE_TOLERANCE
        checks.append(_check("EXPORT_CONTROL", "PASS" if ok else "FAIL",
                             {"rows": exp_rows, "balance": str(exp_sum)}, {"rows": len(curated_rows), "balance": str(cur_sum)},
                             "curated vs the control totals written at export time (pipeline integrity)"))

    bad_bands = []
    for r in curated_rows:
        if r["is_delinquent"] != "true":
            continue
        want = expected_severity(int(r["days_past_due"]))
        if want and r["delinquency_severity"] != want:
            bad_bands.append({"mortgageExternalId": r["mortgage_external_id"], "daysPastDue": int(r["days_past_due"]),
                              "severity": r["delinquency_severity"], "expected": want})
    checks.append(_check("DQ_SEVERITY_BAND", "WARN" if bad_bands else "PASS", "severity matches the days-past-due band",
                         bad_bands, f"{len(bad_bands)} mortgage(s) labelled outside their band (source data; not changed "
                                    "by the pipeline)"))

    failed = [c["check"] for c in checks if c["status"] == "FAIL"]
    return {
        "result": "FAIL" if failed else "PASS",
        "failedChecks": failed,
        "warnings": [c["check"] for c in checks if c["status"] == "WARN"],
        "reportDate": manifest.get("reportDate"),
        "pipelineRunId": manifest.get("pipelineRunId"),
        "schemaVersion": manifest.get("schemaVersion"),
        "reconciledAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
    }


def main(argv=None) -> int:
    from sqlalchemy import text

    from src.api.dependencies import SessionLocal
    from src.services.curated_report import CuratedReportReader

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args(argv)
    reader = CuratedReportReader()
    try:
        day = args.date or reader.available_dates()[-1]
        base = f"{reader.prefix}date={day}/"
        manifest = json.loads(reader._call("get_object", Bucket=reader.bucket, Key=f"{base}_manifest.json")["Body"].read())
        body = reader._call("get_object", Bucket=reader.bucket, Key=manifest["files"][0])["Body"].read().decode("utf-8")
        curated_rows = list(csv.DictReader(io.StringIO(body)))
        try:
            export_manifest = json.loads(reader._call(
                "get_object", Bucket=reader.bucket, Key=f"{os.getenv('RAW_PREFIX', 'raw/pg-export/')}date={day}/_export_manifest.json")["Body"].read())
        except Exception:
            export_manifest = None
    except Exception as exc:  # cannot read the curated zone: not a reconciliation result
        print(json.dumps({"result": "ERROR", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2
    with SessionLocal() as session:
        pg_rows = [dict(r._mapping) for r in session.execute(
            text("SELECT mortgage_external_id, outstanding_balance FROM mortgage"))]
        pg_delinquent = session.execute(text("SELECT count(*) FROM delinquency")).scalar_one()
    report = reconcile(pg_rows, int(pg_delinquent), curated_rows, manifest, export_manifest)
    print(json.dumps(report, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
