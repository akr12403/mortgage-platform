"""M8 Task 8.6: reconciliation PostgreSQL vs curated (pure function; no database or AWS)."""
from decimal import Decimal

from src.services.reconcile import expected_severity, reconcile


def curated(mid, balance, delinquent=False, days=0, severity="NONE"):
    return {"mortgage_external_id": mid, "outstanding_balance": balance, "is_delinquent": "true" if delinquent else "false",
            "days_past_due": str(days), "delinquency_severity": severity}


PG = [{"mortgage_external_id": "MTG-1001", "outstanding_balance": Decimal("304999.96")},
      {"mortgage_external_id": "MTG-1002", "outstanding_balance": Decimal("277150.00")},
      {"mortgage_external_id": "MTG-1005", "outstanding_balance": Decimal("348000.00")}]
CURATED = [curated("MTG-1001", "304999.96"), curated("MTG-1002", "277150.00", True, 45, "MODERATE"),
           curated("MTG-1005", "348000.00", True, 88, "SEVERE")]
MANIFEST = {"rowCount": 3, "reportDate": "2026-11-04", "pipelineRunId": "pr-1", "schemaVersion": 1}
EXPORT = {"rowCounts": {"mortgage": 3}, "mortgageOutstandingBalanceTotal": "930149.96"}


def statuses(report):
    return {c["check"]: c["status"] for c in report["checks"]}


def test_matching_data_passes_every_check():
    report = reconcile(PG, 2, CURATED, MANIFEST, EXPORT)
    assert report["result"] == "PASS" and report["failedChecks"] == [] and report["warnings"] == []
    assert set(statuses(report).values()) == {"PASS"}
    assert len(report["checks"]) == 8


def test_missing_row_fails_count_sum_and_key_set():
    report = reconcile(PG, 2, CURATED[:2], dict(MANIFEST, rowCount=2), EXPORT)
    assert report["result"] == "FAIL"
    assert {"ROW_COUNT", "BALANCE_SUM", "KEY_SET", "EXPORT_CONTROL"} <= set(report["failedChecks"])
    key_set = next(c for c in report["checks"] if c["check"] == "KEY_SET")
    assert key_set["actual"]["missingFromCurated"] == ["MTG-1005"]


def test_balance_tolerance_is_one_cent_in_total_and_per_row():
    within = [dict(CURATED[0], outstanding_balance="304999.97")] + CURATED[1:]       # +0.01 -> inside tolerance
    assert reconcile(PG, 2, within, MANIFEST)["result"] == "PASS"
    outside = [dict(CURATED[0], outstanding_balance="304999.98")] + CURATED[1:]      # +0.02 -> outside
    report = reconcile(PG, 2, outside, MANIFEST)
    assert {"BALANCE_SUM", "ROW_BALANCE"} <= set(report["failedChecks"])


def test_offsetting_row_errors_are_caught_even_when_the_total_matches():
    swapped = [dict(CURATED[0], outstanding_balance="305999.96"), dict(CURATED[1], outstanding_balance="276150.00"),
               CURATED[2]]
    report = reconcile(PG, 2, swapped, MANIFEST)
    assert statuses(report)["BALANCE_SUM"] == "PASS" and report["failedChecks"] == ["ROW_BALANCE"]


def test_delinquent_count_and_manifest_mismatch_fail():
    report = reconcile(PG, 3, CURATED, dict(MANIFEST, rowCount=4))
    assert set(report["failedChecks"]) == {"DELINQUENT_COUNT", "MANIFEST"}


def test_severity_outside_its_band_is_a_warning_not_a_failure():
    mislabelled = CURATED[:2] + [curated("MTG-1005", "348000.00", True, 88, "CRITICAL")]
    report = reconcile(PG, 2, mislabelled, MANIFEST, EXPORT)
    assert report["result"] == "PASS" and report["warnings"] == ["DQ_SEVERITY_BAND"]
    band = next(c for c in report["checks"] if c["check"] == "DQ_SEVERITY_BAND")
    assert band["actual"] == [{"mortgageExternalId": "MTG-1005", "daysPastDue": 88, "severity": "CRITICAL",
                               "expected": "SEVERE"}]


def test_severity_bands_follow_the_playbook():
    assert [expected_severity(d) for d in (0, 29, 30, 59, 60, 89, 90, 400)] == \
        [None, None, "MODERATE", "MODERATE", "SEVERE", "SEVERE", "CRITICAL", "CRITICAL"]
