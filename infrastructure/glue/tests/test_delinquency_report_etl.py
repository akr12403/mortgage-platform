"""Unit tests for the Glue ETL (stdlib only, S3 faked).

    python3 -m unittest discover -s infrastructure/glue/tests -v
"""
import io
import json
import sys
import unittest
from pathlib import Path

GLUE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GLUE_DIR))
import delinquency_report_etl as etl  # noqa: E402

SCHEMA_TEXT = (GLUE_DIR / "schemas" / "delinquency_report.schema.json").read_text()
BUCKET, RAW, CUR, SCHEMA_KEY, DAY = "lake", "raw/pg-export/", "curated/delinquency_report/", "glue/schemas/s.json", "2026-11-04"

MORTGAGE = """id,mortgage_external_id,borrower_id,status,original_amount,outstanding_balance,origination_date
m1,MTG-1001,b1,ACTIVE,310000.00,304999.96,2024-01-15
m2,MTG-1002,b2,DELINQUENT,280000.00,277150.00,2023-06-01
m3,MTG-1003,b1,ACTIVE,150000.00,149000.50,2025-02-01
"""
BORROWER = "id,borrower_external_id\nb1,BOR-001\nb2,BOR-002\n"
DELINQUENCY = "mortgage_id,delinquent_since,days_past_due,severity\nm2,2026-08-01,95,CRITICAL\n"
PAYMENT = """mortgage_id,due_date,paid_date,amount,status
m1,2026-10-01,2026-10-01,1850.00,POSTED
m1,2026-11-01,2026-11-02,1850.00,POSTED
m2,2026-11-01,2026-11-03,1850.00,POSTED
m2,2026-10-01,,1850.00,FAILED
"""


class FakeS3:
    def __init__(self, objects):
        self.objects = dict(objects)
        self.deleted = []

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(f"NoSuchKey {Key}")
        return {"Body": io.BytesIO(self.objects[Key].encode() if isinstance(self.objects[Key], str) else self.objects[Key])}

    def put_object(self, Bucket, Key, Body, **kwargs):
        assert kwargs.get("ServerSideEncryption") == "AES256"
        self.objects[Key] = Body.decode()

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in self.objects if k.startswith(Prefix)]}

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key)


def lake(**overrides):
    files = {"mortgage": MORTGAGE, "borrower": BORROWER, "delinquency": DELINQUENCY, "payment": PAYMENT}
    files.update(overrides)
    objects = {f"{RAW}date={DAY}/{t}.csv": text for t, text in files.items()}
    objects[SCHEMA_KEY] = SCHEMA_TEXT
    return FakeS3(objects)


def run(s3, drift_mode="fail"):
    out = io.StringIO()
    old, sys.stdout = sys.stdout, out
    try:
        manifest = etl.run(s3, BUCKET, RAW, CUR, SCHEMA_KEY, DAY, "jr_test", drift_mode)
    finally:
        sys.stdout = old
    return manifest, [json.loads(line) for line in out.getvalue().splitlines()]


def curated_rows(s3):
    import csv
    return list(csv.DictReader(io.StringIO(s3.objects[f"{CUR}date={DAY}/part-0000.csv"])))


class EtlTests(unittest.TestCase):
    def test_one_row_per_mortgage_with_derived_columns(self):
        s3 = lake()
        manifest, _ = run(s3)
        rows = {r["mortgage_external_id"]: r for r in curated_rows(s3)}
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows["MTG-1002"]["borrower_external_id"], "BOR-002")
        self.assertEqual((rows["MTG-1002"]["is_delinquent"], rows["MTG-1002"]["days_past_due"],
                          rows["MTG-1002"]["delinquency_severity"], rows["MTG-1002"]["risk_bucket"]),
                         ("true", "95", "CRITICAL", "DPD_90_PLUS"))
        self.assertEqual((rows["MTG-1001"]["risk_bucket"], rows["MTG-1001"]["delinquency_severity"]), ("CURRENT", "NONE"))
        self.assertEqual(rows["MTG-1001"]["last_payment_date"], "2026-11-02")
        self.assertEqual(rows["MTG-1001"]["posted_payment_total"], "3700.00")
        self.assertEqual(rows["MTG-1002"]["posted_payment_total"], "1850.00")  # FAILED payment not counted
        self.assertEqual(rows["MTG-1003"]["last_payment_date"], "")
        self.assertEqual(manifest["rowCount"], 3)
        self.assertEqual(manifest["outstandingBalanceTotal"], "731150.46")
        self.assertEqual(manifest["sourceRowCounts"], {"mortgage": 3, "borrower": 2, "delinquency": 1, "payment": 4})

    def test_header_matches_the_committed_schema_order(self):
        s3 = lake()
        run(s3)
        header = s3.objects[f"{CUR}date={DAY}/part-0000.csv"].splitlines()[0].split(",")
        self.assertEqual(header, [c["name"] for c in json.loads(SCHEMA_TEXT)["columns"]])

    def test_rerun_replaces_the_date_partition(self):
        s3 = lake()
        s3.objects[f"{CUR}date={DAY}/part-0001.csv"] = "stale"
        run(s3)
        self.assertIn(f"{CUR}date={DAY}/part-0001.csv", s3.deleted)
        self.assertEqual(sorted(k for k in s3.objects if k.startswith(CUR)),
                         [f"{CUR}date={DAY}/_manifest.json", f"{CUR}date={DAY}/part-0000.csv"])

    def test_missing_input_column_fails_the_run(self):
        s3 = lake(mortgage=MORTGAGE.replace("outstanding_balance", "balance"))
        with self.assertRaises(etl.SchemaContractError) as ctx:
            run(s3)
        self.assertIn("outstanding_balance", str(ctx.exception))
        self.assertFalse(any(k.startswith(CUR) for k in s3.objects))  # nothing half-written

    def test_output_validation_rejects_bad_values(self):
        schema = json.loads(SCHEMA_TEXT)
        good = etl.transform(DAY, {"mortgage": [dict(id="m1", mortgage_external_id="MTG-1001", borrower_id="b1",
                                                     status="ACTIVE", original_amount="1", outstanding_balance="1",
                                                     origination_date="2024-01-01")],
                                   "borrower": [dict(id="b1", borrower_external_id="BOR-001")],
                                   "delinquency": [], "payment": []})
        etl.validate_output(good, schema)
        for column, value in (("status", "UNKNOWN"), ("outstanding_balance", "1.5"), ("mortgage_external_id", "X-1"),
                              ("report_date", "04/11/2026"), ("borrower_external_id", "")):
            bad = [dict(good[0], **{column: value})]
            with self.subTest(column=column), self.assertRaises(etl.SchemaContractError):
                etl.validate_output(bad, schema)

    def test_unknown_borrower_reference_fails(self):
        with self.assertRaises(etl.SchemaContractError):
            run(lake(borrower="id,borrower_external_id\nb1,BOR-001\n"))

    def test_structured_log_lines(self):
        _, logs = run(lake())
        self.assertEqual([l["message"] for l in logs], ["ETL started", "ETL finished"])
        self.assertEqual(logs[-1]["rowCount"], 3)
        self.assertEqual(logs[-1]["service"], "glue-delinquency-etl")
        self.assertEqual({l["pipelineRunId"] for l in logs}, {"jr_test"})

    def test_main_parses_glue_arguments_and_ignores_extras(self):
        captured = {}
        original = etl.run
        etl.run = lambda *a: captured.setdefault("args", a)
        try:
            sys.modules["boto3"] = type(sys)("boto3")
            sys.modules["boto3"].client = lambda name: "s3-client"
            etl.main(["--RUN_DATE", DAY, "--BUCKET", BUCKET, "--RAW_PREFIX", RAW, "--CURATED_PREFIX", CUR,
                      "--SCHEMA_KEY", SCHEMA_KEY, "--job-bookmark-option", "job-bookmark-disable", "--PIPELINE_RUN_ID", "pr_1"])
        finally:
            etl.run = original
            del sys.modules["boto3"]
        self.assertEqual(captured["args"], ("s3-client", BUCKET, RAW, CUR, SCHEMA_KEY, DAY, "pr_1", "fail"))


DRIFTED_MORTGAGE = "\n".join(line + (",property_state" if i == 0 else ",CA") if line else line
                             for i, line in enumerate(MORTGAGE.split("\n")))


class SchemaDriftTests(unittest.TestCase):
    """Task 8.6: a column added to the export (before/after documented in the pipeline runbook)."""

    def test_added_column_fails_the_run_in_strict_mode_and_writes_nothing(self):
        s3 = lake(mortgage=DRIFTED_MORTGAGE)
        s3.objects[f"{CUR}date={DAY}/part-0000.csv"] = "previous good output"
        with self.assertRaises(etl.SchemaDriftError) as ctx:
            run(s3)
        self.assertIn("property_state", str(ctx.exception))
        self.assertEqual(s3.objects[f"{CUR}date={DAY}/part-0000.csv"], "previous good output")  # untouched
        self.assertEqual(s3.deleted, [])

    def test_evolve_mode_tolerates_the_added_column_and_records_it(self):
        s3 = lake(mortgage=DRIFTED_MORTGAGE)
        manifest, logs = run(s3, drift_mode="evolve")
        self.assertEqual(manifest["schemaDrift"], {"mortgage": ["property_state"]})
        self.assertEqual(manifest["schemaDriftMode"], "evolve")
        self.assertEqual(manifest["rowCount"], 3)
        self.assertNotIn("property_state", s3.objects[f"{CUR}date={DAY}/part-0000.csv"])  # output contract unchanged
        self.assertIn("WARN", [l["level"] for l in logs])

    def test_evolve_mode_never_tolerates_a_missing_column(self):
        with self.assertRaises(etl.SchemaContractError):
            run(lake(mortgage=MORTGAGE.replace(",status,", ",state,")), drift_mode="evolve")

    def test_no_drift_records_an_empty_drift_map(self):
        manifest, _ = run(lake())
        self.assertEqual(manifest["schemaDrift"], {})

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            run(lake(), drift_mode="ignore")


if __name__ == "__main__":
    unittest.main(verbosity=2)
