"""Repository-level contract checks for M5 lifecycle events.

Run from the repo root:  python -m pytest -q tests/contract   (needs: pytest, jsonschema)

Checks that
  * every schema is a valid JSON Schema (draft 2020-12),
  * every example in docs/architecture/events/examples validates against its schema,
  * the event catalog lists exactly the implemented events and links every schema,
  * the Java producer payload records declare exactly the schema's required payload fields,
  * servicing-service maps every cataloged event type,
  * each service publishes an OpenAPI contract named {service}-openapi.yaml.
"""
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / "docs" / "architecture" / "events"
CATALOG = ROOT / "docs" / "architecture" / "event-catalog.md"
PAYLOADS_JAVA = ROOT / "services/mortgage-service/src/main/java/com/capstone/mortgage/events/EventPayloads.java"
CONSUMER_JAVA = ROOT / "services/servicing-service/src/main/java/com/capstone/servicing/service/EventConsumerService.java"

EVENT_FILES = {
    "MortgageCreated": "mortgage-created",
    "LoanApproved": "loan-approved",
    "PaymentReceived": "payment-received",
    "PaymentMissed": "payment-missed",
    "LoanDelinquent": "loan-delinquent",
}


def load(path):
    return json.loads(Path(path).read_text())


@pytest.mark.parametrize("event_type", sorted(EVENT_FILES))
def test_schema_is_valid_and_example_conforms(event_type):
    stem = EVENT_FILES[event_type]
    schema = load(EVENTS / f"{stem}.schema.json")
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["eventType"]["const"] == event_type

    example = load(EVENTS / "examples" / f"{stem}.json")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(example))
    assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("event_type", sorted(EVENT_FILES))
def test_schema_rejects_internal_uuid_as_mortgage_id(event_type):
    stem = EVENT_FILES[event_type]
    schema = load(EVENTS / f"{stem}.schema.json")
    example = load(EVENTS / "examples" / f"{stem}.json")
    example["payload"]["mortgageExternalId"] = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    assert list(Draft202012Validator(schema).iter_errors(example)), "UUID must not be accepted as mortgageExternalId"


def test_catalog_matches_implemented_events():
    text = CATALOG.read_text()
    cataloged = set(re.findall(r"^\| `(\w+)` \| `(\d+\.\d+)`", text, flags=re.M))
    assert {name for name, _ in cataloged} == set(EVENT_FILES)
    for stem in EVENT_FILES.values():
        assert f"{stem}.schema.json" in text
    assert "Planned" not in text and "not wired" not in text


def _java_records(source):
    records = {}
    for name, params in re.findall(r"record\s+(\w+)\s*\(([^)]*)\)", source, flags=re.S):
        fields = [p.strip().split()[-1] for p in params.split(",") if p.strip()]
        records[name] = fields
    return records


@pytest.mark.parametrize("event_type", sorted(EVENT_FILES))
def test_java_producer_payload_matches_schema(event_type):
    records = _java_records(PAYLOADS_JAVA.read_text())
    java_fields = records[f"{event_type}Payload"]
    schema = load(EVENTS / f"{EVENT_FILES[event_type]}.schema.json")
    assert sorted(java_fields) == sorted(schema["properties"]["payload"]["required"])


def test_servicing_consumer_handles_every_cataloged_event():
    source = CONSUMER_JAVA.read_text()
    for event_type in EVENT_FILES:
        assert f'"{event_type}"' in source, f"{event_type} not mapped in EventConsumerService"


@pytest.mark.parametrize("service", ["mortgage-service", "servicing-service", "mortgage-analytics-service"])
def test_openapi_contract_published(service):
    spec = ROOT / "docs" / "api" / f"{service}-openapi.yaml"
    assert spec.exists()
    text = spec.read_text()
    assert text.startswith("openapi: 3.") and "version: v1" in text
