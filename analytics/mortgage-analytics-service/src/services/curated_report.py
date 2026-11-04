"""M8 Task 8.5: read the curated delinquency report written by the Glue job.

s3://capstone-mortgage-analytics-dev/curated/delinquency_report/date=YYYY-MM-DD/{part-0000.csv,_manifest.json}

The analytics service only reads this zone (mortgage-analytics-role: s3:GetObject on curated/delinquency_report/*,
s3:ListBucket restricted to that prefix); it never writes it. The report is computed from the curated file, not
from PostgreSQL, so it shows exactly what the pipeline produced for that date.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from decimal import Decimal
from typing import Optional

from src.services.s3_service import get_s3_client

REQUIRED_COLUMNS = ("mortgage_external_id", "status", "outstanding_balance", "is_delinquent", "days_past_due",
                    "delinquency_severity", "risk_bucket")
RISK_BUCKETS = ("CURRENT", "DPD_30_59", "DPD_60_89", "DPD_90_PLUS")
_DATE_PREFIX = re.compile(r"date=(\d{4}-\d{2}-\d{2})/$")


class CuratedUnavailableError(RuntimeError):
    """S3 could not be read (not configured here, no access, network)."""


class CuratedNotFoundError(LookupError):
    """No curated partition for the requested date (or none at all)."""


class CuratedSchemaError(ValueError):
    """The curated file does not have the columns this report needs (schema drift upstream)."""


class CuratedReportReader:
    def __init__(self, s3=None, bucket: Optional[str] = None, prefix: Optional[str] = None):
        self._s3 = s3
        self.bucket = bucket or os.getenv("S3_BUCKET_ANALYTICS", "capstone-mortgage-analytics-dev")
        self.prefix = prefix or os.getenv("CURATED_PREFIX", "curated/delinquency_report/")

    @property
    def s3(self):
        if self._s3 is None:
            self._s3 = get_s3_client()
        return self._s3

    def _call(self, method, **kwargs):
        try:
            return getattr(self.s3, method)(**kwargs)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise CuratedNotFoundError(kwargs.get("Key", "")) from exc
            raise CuratedUnavailableError(f"{type(exc).__name__} {code}".strip()) from exc

    def available_dates(self) -> list:
        response = self._call("list_objects_v2", Bucket=self.bucket, Prefix=self.prefix, Delimiter="/")
        dates = []
        for common in response.get("CommonPrefixes", []):
            match = _DATE_PREFIX.search(common["Prefix"])
            if match:
                dates.append(match.group(1))
        return sorted(dates)

    def report(self, report_date: Optional[str] = None) -> dict:
        if report_date is None:
            dates = self.available_dates()
            if not dates:
                raise CuratedNotFoundError("no curated partitions yet")
            report_date = dates[-1]
        base = f"{self.prefix}date={report_date}/"
        manifest = json.loads(self._call("get_object", Bucket=self.bucket, Key=f"{base}_manifest.json")["Body"].read())
        data_key = manifest.get("files", [f"{base}part-0000.csv"])[0]
        text = self._call("get_object", Bucket=self.bucket, Key=data_key)["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise CuratedSchemaError(f"curated file lacks {missing}")
        rows = list(reader)
        return summarize(rows, report_date, manifest, f"s3://{self.bucket}/{data_key}")


def summarize(rows: list, report_date: str, manifest: dict, location: str) -> dict:
    total = sum((Decimal(r["outstanding_balance"]) for r in rows), Decimal("0"))
    delinquent = [r for r in rows if r["is_delinquent"] == "true"]
    at_risk = sum((Decimal(r["outstanding_balance"]) for r in delinquent), Decimal("0"))
    buckets = {b: {"count": 0, "outstandingBalance": Decimal("0")} for b in RISK_BUCKETS}
    for r in rows:
        bucket = buckets.setdefault(r["risk_bucket"], {"count": 0, "outstandingBalance": Decimal("0")})
        bucket["count"] += 1
        bucket["outstandingBalance"] += Decimal(r["outstanding_balance"])
    severity = {}
    for r in delinquent:
        severity[r["delinquency_severity"]] = severity.get(r["delinquency_severity"], 0) + 1
    top = sorted(delinquent, key=lambda r: (-int(r["days_past_due"]), r["mortgage_external_id"]))[:5]
    return {
        "reportDate": report_date,
        "mortgageCount": len(rows),
        "delinquentCount": len(delinquent),
        "delinquencyRate": round(len(delinquent) / len(rows), 4) if rows else 0.0,
        "outstandingBalanceTotal": float(total),
        "balanceAtRisk": float(at_risk),
        "byRiskBucket": {k: {"count": v["count"], "outstandingBalance": float(v["outstandingBalance"])}
                         for k, v in buckets.items()},
        "bySeverity": severity,
        "mostPastDue": [{"mortgageExternalId": r["mortgage_external_id"], "daysPastDue": int(r["days_past_due"]),
                         "severity": r["delinquency_severity"], "outstandingBalance": float(Decimal(r["outstanding_balance"]))}
                        for r in top],
        "source": {"location": location, "dataset": manifest.get("dataset"), "schemaVersion": manifest.get("schemaVersion"),
                   "generatedAt": manifest.get("generatedAt"), "pipelineRunId": manifest.get("pipelineRunId"),
                   "manifestRowCount": manifest.get("rowCount")},
    }
