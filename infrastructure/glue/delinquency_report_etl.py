"""M8 Task 8.5: Glue Python shell job capstone-mortgage-delinquency-etl-dev (Python 3.9, 0.0625 DPU).

raw   s3://<bucket>/raw/pg-export/date=YYYY-MM-DD/{mortgage,borrower,delinquency,payment}.csv   (PostgreSQL export)
  ->  join + derive (one row per mortgage)
curated s3://<bucket>/curated/delinquency_report/date=YYYY-MM-DD/part-0000.csv + _manifest.json

The column contract lives in glue/schemas/delinquency_report.schema.json (committed copy:
infrastructure/glue/schemas/). The job checks the input columns against it before transforming, and checks every
output row against it before writing. A re-run for the same date replaces that date's curated objects (idempotent).

Standard library + boto3 only (boto3 comes with the Glue "analytics" library set). Written for Python 3.9.
Job arguments: --RUN_DATE YYYY-MM-DD, --BUCKET, --RAW_PREFIX, --CURATED_PREFIX, --SCHEMA_KEY, optional
--PIPELINE_RUN_ID (set by scripts/aws/pipeline-run.sh; Glue does not pass its own run id to Python shell jobs) and
--SCHEMA_DRIFT_MODE fail|evolve (Task 8.6, default fail):
  * a MISSING required input column always fails the run;
  * an UNEXPECTED (added) input column fails the run in "fail" mode (fail-with-alert: the run state FAILED triggers
    the EventBridge alert rule) and is tolerated in "evolve" mode: ignored for the output, logged at WARN and
    recorded in the curated manifest under schemaDrift, so the owner can add it to the schema in a PR.
IAM: mortgage-glue-etl-role (read raw + glue/ assets, write/delete curated only, write Glue logs).
"""
import argparse
import csv
import io
import json
import re
import sys
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
TABLES = ("mortgage", "borrower", "delinquency", "payment")


class SchemaContractError(Exception):
    """Input or output does not match the committed schema: the run fails (Glue run state FAILED)."""


class SchemaDriftError(SchemaContractError):
    """The raw export has columns the schema does not know (strict mode)."""


def log(level, message, **fields):
    record = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": level,
              "service": "glue-delinquency-etl", "message": message}
    record.update({k: v for k, v in fields.items() if v is not None})
    print(json.dumps(record, default=str), flush=True)


def money(value):
    return Decimal(str(value or "0")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def risk_bucket(days_past_due):
    if days_past_due >= 90:
        return "DPD_90_PLUS"
    if days_past_due >= 60:
        return "DPD_60_89"
    if days_past_due >= 30:
        return "DPD_30_59"
    return "CURRENT"


# ---------------------------------------------------------------- input

def read_csv(text, table, required_columns):
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    missing = [c for c in required_columns if c not in columns]
    if missing:
        raise SchemaContractError(f"{table}.csv is missing required column(s) {missing}; got {columns}")
    return columns, list(reader)


def unexpected_columns(columns, required_columns):
    return [c for c in columns if c not in required_columns]


# ---------------------------------------------------------------- transform

def transform(report_date, tables):
    """tables: {name: [row dicts]} -> list of output rows (dicts), one per mortgage, sorted by mortgage id."""
    borrowers = {b["id"]: b["borrower_external_id"] for b in tables["borrower"]}
    delinquency = {d["mortgage_id"]: d for d in tables["delinquency"]}
    posted_total, last_paid = {}, {}
    for p in tables["payment"]:
        if p["status"] != "POSTED":
            continue
        posted_total[p["mortgage_id"]] = posted_total.get(p["mortgage_id"], Decimal("0")) + money(p["amount"])
        if p.get("paid_date") and p["paid_date"] > last_paid.get(p["mortgage_id"], ""):
            last_paid[p["mortgage_id"]] = p["paid_date"]

    rows = []
    for m in tables["mortgage"]:
        if m["borrower_id"] not in borrowers:
            raise SchemaContractError(f"mortgage {m['mortgage_external_id']} references an unknown borrower")
        d = delinquency.get(m["id"])
        days = int(d["days_past_due"]) if d else 0
        rows.append({
            "report_date": report_date,
            "mortgage_external_id": m["mortgage_external_id"],
            "borrower_external_id": borrowers[m["borrower_id"]],
            "status": m["status"],
            "original_amount": str(money(m["original_amount"])),
            "outstanding_balance": str(money(m["outstanding_balance"])),
            "is_delinquent": "true" if d else "false",
            "days_past_due": str(days),
            "delinquency_severity": d["severity"] if d else "NONE",
            "delinquent_since": d["delinquent_since"] if d else "",
            "risk_bucket": risk_bucket(days),
            "last_payment_date": last_paid.get(m["id"], ""),
            "posted_payment_total": str(posted_total.get(m["id"], Decimal("0.00")).quantize(TWO_PLACES)),
        })
    rows.sort(key=lambda r: r["mortgage_external_id"])
    return rows


# ---------------------------------------------------------------- output contract

_TYPE_CHECKS = {
    "string": lambda v: True,
    "date": lambda v: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)),
    "integer": lambda v: bool(re.fullmatch(r"-?\d+", v)),
    "boolean": lambda v: v in ("true", "false"),
}


def validate_output(rows, schema):
    names = [c["name"] for c in schema["columns"]]
    seen = set()
    for i, row in enumerate(rows):
        if list(row) != names:
            raise SchemaContractError(f"row {i}: columns {list(row)} differ from schema {names}")
        key = tuple(row[k] for k in schema["primaryKey"])
        if key in seen:
            raise SchemaContractError(f"duplicate primary key {key}")
        seen.add(key)
        for col in schema["columns"]:
            value = row[col["name"]]
            if value == "":
                if not col["nullable"]:
                    raise SchemaContractError(f"row {i}: {col['name']} is empty but not nullable")
                continue
            kind = col["type"]
            ok = (bool(re.fullmatch(r"-?\d+\.\d{2}", value)) if kind.startswith("decimal")
                  else _TYPE_CHECKS[kind](value))
            if not ok or ("enum" in col and value not in col["enum"]) or \
                    ("pattern" in col and not re.fullmatch(col["pattern"], value)):
                raise SchemaContractError(f"row {i}: {col['name']}={value!r} violates {kind} {col.get('enum') or col.get('pattern') or ''}")


def to_csv(rows, schema):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=[c["name"] for c in schema["columns"]], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


# ---------------------------------------------------------------- job

def run(s3, bucket, raw_prefix, curated_prefix, schema_key, report_date, pipeline_run_id="local", drift_mode="fail"):
    date.fromisoformat(report_date)  # validates YYYY-MM-DD
    if drift_mode not in ("fail", "evolve"):
        raise ValueError(f"SCHEMA_DRIFT_MODE must be fail or evolve, not {drift_mode!r}")
    schema = json.loads(s3.get_object(Bucket=bucket, Key=schema_key)["Body"].read())
    raw_dir = f"{raw_prefix}date={report_date}/"
    out_dir = f"{curated_prefix}date={report_date}/"
    log("INFO", "ETL started", reportDate=report_date, raw=f"s3://{bucket}/{raw_dir}", pipelineRunId=pipeline_run_id,
        schemaVersion=schema["version"], schemaDriftMode=drift_mode)

    tables, source_counts, drift = {}, {}, {}
    for table in TABLES:
        key = f"{raw_dir}{table}.csv"
        text = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        columns, rows = read_csv(text, table, schema["sources"][table])
        extra = unexpected_columns(columns, schema["sources"][table])
        if extra:
            drift[table] = extra
        tables[table] = rows
        source_counts[table] = len(rows)
    if drift:
        if drift_mode == "fail":
            raise SchemaDriftError(f"unexpected column(s) in the raw export {drift} (schema v{schema['version']}); "
                                   "add them to the schema (version bump) or re-run with SCHEMA_DRIFT_MODE=evolve")
        log("WARN", "Schema drift tolerated (evolve mode): extra columns ignored", schemaDrift=drift,
            schemaVersion=schema["version"], pipelineRunId=pipeline_run_id)

    rows = transform(report_date, tables)
    validate_output(rows, schema)
    balance_total = sum((Decimal(r["outstanding_balance"]) for r in rows), Decimal("0.00"))

    # Idempotent re-run: remove this date's previous output first.
    listed = s3.list_objects_v2(Bucket=bucket, Prefix=out_dir).get("Contents", [])
    for obj in listed:
        s3.delete_object(Bucket=bucket, Key=obj["Key"])

    data_key = f"{out_dir}part-0000.csv"
    s3.put_object(Bucket=bucket, Key=data_key, Body=to_csv(rows, schema).encode("utf-8"),
                  ContentType="text/csv", ServerSideEncryption="AES256")
    manifest = {
        "dataset": schema["name"], "schemaVersion": schema["version"], "reportDate": report_date,
        "rowCount": len(rows), "outstandingBalanceTotal": str(balance_total),
        "delinquentCount": sum(1 for r in rows if r["is_delinquent"] == "true"),
        "sourceRowCounts": source_counts, "files": [data_key], "pipelineRunId": pipeline_run_id,
        "schemaDriftMode": drift_mode, "schemaDrift": drift,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    s3.put_object(Bucket=bucket, Key=f"{out_dir}_manifest.json", Body=json.dumps(manifest, indent=2).encode("utf-8"),
                  ContentType="application/json", ServerSideEncryption="AES256")
    log("INFO", "ETL finished", reportDate=report_date, rowCount=len(rows), outstandingBalanceTotal=str(balance_total),
        delinquentCount=manifest["delinquentCount"], pipelineRunId=pipeline_run_id, curated=f"s3://{bucket}/{data_key}", replacedObjects=len(listed))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("RUN_DATE", "BUCKET", "RAW_PREFIX", "CURATED_PREFIX", "SCHEMA_KEY"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--PIPELINE_RUN_ID", default="unknown")
    parser.add_argument("--SCHEMA_DRIFT_MODE", default="fail")
    args, _ = parser.parse_known_args(argv)  # Glue adds its own arguments (--job-bookmark-option, ...)
    import boto3
    try:
        run(boto3.client("s3"), args.BUCKET, args.RAW_PREFIX, args.CURATED_PREFIX, args.SCHEMA_KEY, args.RUN_DATE,
            args.PIPELINE_RUN_ID, args.SCHEMA_DRIFT_MODE)
    except Exception as exc:
        log("ERROR", "ETL failed", errorType=type(exc).__name__, error=str(exc)[:500], reportDate=args.RUN_DATE,
            pipelineRunId=args.PIPELINE_RUN_ID)
        raise


if __name__ == "__main__":
    main(sys.argv[1:])
