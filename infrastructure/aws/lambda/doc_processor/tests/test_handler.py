"""Unit tests for the document processor Lambda (stdlib only; S3 and DynamoDB are faked).

    python3 -m unittest discover -s infrastructure/aws/lambda/doc_processor/tests -v
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import handler  # noqa: E402

PDF = b"%PDF-1.4\n%synthetic test document\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeS3:
    def __init__(self, body, content_type, metadata=None):
        self.body, self.content_type, self.metadata, self.calls = body, content_type, metadata or {}, []

    def get_object(self, **kwargs):
        self.calls.append(kwargs)
        end = int(kwargs["Range"].split("-")[1]) + 1 if "Range" in kwargs else None
        return {"Body": io.BytesIO(self.body[:end]), "ContentType": self.content_type,
                "Metadata": self.metadata, "ServerSideEncryption": "AES256"}


class FakeDynamo:
    def __init__(self, fail=False):
        self.items, self.fail = [], fail

    def put_item(self, TableName, Item):
        if self.fail:
            raise RuntimeError("ProvisionedThroughputExceeded (simulated)")
        self.items.append((TableName, Item))


class Ctx:
    aws_request_id = "req-123"


def event(key, size, name="ObjectCreated:Put"):
    return {"Records": [{"eventName": name, "eventTime": "2026-11-03T02:00:00.000Z",
                         "s3": {"bucket": {"name": "capstone-mortgage-docs-dev"},
                                "object": {"key": key, "size": size, "eTag": "abc123"}}}]}


KEY = "mortgages/MTG-1002/0f8fad5b-d9cb-469f-a165-70867728950e-deed.pdf"


class HandlerTests(unittest.TestCase):
    def run_handler(self, s3, dynamo, evt):
        handler._clients = {"s3": s3, "dynamodb": dynamo}
        out = io.StringIO()
        with redirect_stdout(out):
            result = handler.lambda_handler(evt, Ctx())
        logs = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        return result, logs

    def test_valid_pdf_is_validated_and_stored(self):
        s3, db = FakeS3(PDF, "application/pdf", {"correlation-id": "cid-42", "document-type": "DEED"}), FakeDynamo()
        result, logs = self.run_handler(s3, db, event(KEY, len(PDF)))
        self.assertEqual(result["results"][0]["status"], "VALIDATED")
        table, item = db.items[0]
        self.assertEqual(table, "CapstoneMortgageDocumentMetadata-dev")
        self.assertEqual(item["mortgageExternalId"], {"S": "MTG-1002"})
        self.assertEqual(item["s3Key"], {"S": KEY})
        self.assertEqual(item["fileName"], {"S": "deed.pdf"})
        self.assertEqual(item["documentType"], {"S": "DEED"})
        self.assertEqual(item["serverSideEncryption"], {"S": "AES256"})
        self.assertNotIn("rejectReasons", item)
        self.assertIn("expiresAt", item)
        self.assertEqual(s3.calls[0]["Range"], "bytes=0-1023")  # only the first bytes are read

    def test_log_line_has_standard_fields_and_no_content(self):
        s3, db = FakeS3(PDF, "application/pdf", {"correlation-id": "cid-42"}), FakeDynamo()
        _, logs = self.run_handler(s3, db, event(KEY, len(PDF)))
        line = logs[-1]
        for field in ("timestamp", "level", "service", "correlationId", "message", "mortgageId"):
            self.assertIn(field, line)
        self.assertEqual(line["correlationId"], "cid-42")  # traced back to the upload API request
        self.assertEqual(line["level"], "INFO")
        self.assertNotIn("synthetic test document", json.dumps(logs))

    def test_pdf_with_wrong_magic_bytes_is_rejected(self):
        body = b"this is not a pdf"
        s3, db = FakeS3(body, "application/pdf"), FakeDynamo()
        result, logs = self.run_handler(s3, db, event(KEY, len(body)))
        self.assertEqual(result["results"][0]["status"], "REJECTED")
        self.assertEqual(db.items[0][1]["rejectReasons"], {"SS": ["MAGIC_BYTES_MISMATCH"]})
        self.assertEqual(logs[-1]["level"], "WARN")
        self.assertEqual(logs[-1]["correlationId"], "req-123")  # no upload metadata -> Lambda request id

    def test_disallowed_content_type_and_extension_mismatch(self):
        s3, db = FakeS3(b"MZ\x90\x00", "application/x-msdownload"), FakeDynamo()
        result, _ = self.run_handler(s3, db, event(KEY.replace("deed.pdf", "tool.exe"), 4))
        self.assertEqual(result["results"][0]["reasons"], ["CONTENT_TYPE_NOT_ALLOWED:application/x-msdownload"])
        s3, db = FakeS3(PNG, "image/png"), FakeDynamo()
        result, _ = self.run_handler(s3, db, event(KEY.replace("deed.pdf", "scan.pdf"), len(PNG)))
        self.assertEqual(result["results"][0]["reasons"], ["EXTENSION_MISMATCH"])

    def test_text_with_nul_bytes_empty_and_oversized_files(self):
        s3, db = FakeS3(b"hello\x00world", "text/plain"), FakeDynamo()
        result, _ = self.run_handler(s3, db, event(KEY.replace("deed.pdf", "note.txt"), 11))
        self.assertEqual(result["results"][0]["reasons"], ["BINARY_CONTENT_IN_TEXT"])
        s3, db = FakeS3(b"", "text/plain"), FakeDynamo()
        result, _ = self.run_handler(s3, db, event(KEY.replace("deed.pdf", "empty.txt"), 0))
        self.assertEqual(result["results"][0]["reasons"], ["EMPTY_FILE"])
        self.assertNotIn("Range", s3.calls[0])  # a ranged GET on an empty object would fail with 416
        s3, db = FakeS3(PDF, "application/pdf"), FakeDynamo()
        result, _ = self.run_handler(s3, db, event(KEY, handler.MAX_BYTES + 1))
        self.assertEqual(result["results"][0]["reasons"], ["TOO_LARGE"])

    def test_url_encoded_keys_are_decoded(self):
        s3, db = FakeS3(PDF, "application/pdf"), FakeDynamo()
        encoded = "mortgages/MTG-1002/0f8fad5b-d9cb-469f-a165-70867728950e-closing+deed%281%29.pdf"
        result, _ = self.run_handler(s3, db, event(encoded, len(PDF)))
        self.assertEqual(db.items[0][1]["fileName"], {"S": "closing deed(1).pdf"})
        self.assertEqual(s3.calls[0]["Key"], "mortgages/MTG-1002/0f8fad5b-d9cb-469f-a165-70867728950e-closing deed(1).pdf")
        self.assertEqual(result["results"][0]["status"], "VALIDATED")

    def test_objects_outside_the_layout_are_skipped_without_reading(self):
        s3, db = FakeS3(PDF, "application/pdf"), FakeDynamo()
        result, logs = self.run_handler(s3, db, event("mortgages/not-a-mortgage-id/x.pdf", 10))
        self.assertEqual(result["results"][0]["status"], "SKIPPED")
        self.assertEqual(s3.calls, [])
        self.assertEqual(db.items, [])

    def test_non_create_events_are_ignored(self):
        s3, db = FakeS3(PDF, "application/pdf"), FakeDynamo()
        result, _ = self.run_handler(s3, db, event(KEY, 10, name="ObjectRemoved:Delete"))
        self.assertEqual(result["processed"], 0)

    def test_dynamodb_failure_is_logged_and_raised_for_the_errors_alarm(self):
        s3, db = FakeS3(PDF, "application/pdf"), FakeDynamo(fail=True)
        handler._clients = {"s3": s3, "dynamodb": db}
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(RuntimeError):
            handler.lambda_handler(event(KEY, len(PDF)), Ctx())
        line = json.loads(out.getvalue().splitlines()[-1])
        self.assertEqual((line["level"], line["errorType"]), ("ERROR", "RuntimeError"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
