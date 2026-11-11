"""Incident summarization (M7 Task 7.6, Session 27): incident text -> structured summary + runbook links.

    redact -> LLM (prompt incident-summary-v1, strict JSON) -> validate in code -> approval rules -> result

Controls (same idea as the Q&A path, see docs/ai/governance.md):
- Personal data and `name=value` secrets are redacted before the text reaches the LLM or a log line.
- The model may only recommend runbooks from the fixed catalogue (src/ops/runbooks.py); invented ids are dropped.
- Output is validated field by field; values outside the schema are coerced to safe defaults.
- `requiresHumanApproval` is decided by code, not by the model: low confidence (< 0.7), SEV1, unknown severity,
  no runbook match, an invented runbook, or sensitive data found in the log.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from src.ops.prompts import (INCIDENT_PROMPT_VERSION, INCIDENT_RESPONSE_SCHEMA, INCIDENT_SYSTEM_PROMPT,
                             build_incident_user_message)
from src.ops.runbooks import BY_ID, Runbook, catalogue_for_prompt
from src.rag.llm import ChatModel
from src.rag.redaction import redact

log = logging.getLogger(__name__)

APPROVAL_CONFIDENCE = 0.7          # below this a person must confirm the summary before acting (handbook 7.6)
MIN_INCIDENT_CHARS = 20
MAX_INCIDENT_CHARS = 20_000
MAX_ACTIONS = 5
SEVERITIES = ("SEV1", "SEV2", "SEV3", "UNKNOWN")
_INCIDENT_ID = re.compile(r"^INC-\d{4}-\d{4}$")


class IncidentInputError(ValueError):
    """Empty, too short or too long incident text, or a malformed incident id (maps to HTTP 400)."""


@dataclass(frozen=True)
class IncidentSummary:
    incident_id: str | None
    title: str
    severity: str
    summary: str
    impact: str
    timeline: tuple[tuple[str, str], ...]
    suspected_cause: str
    affected_services: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    runbooks: tuple[Runbook, ...]
    confidence: float
    open_questions: tuple[str, ...]
    requires_human_approval: bool
    approval_reasons: tuple[str, ...]
    redacted_types: tuple[str, ...] = ()
    dropped_runbook_ids: tuple[str, ...] = field(default=())
    model: str | None = None
    prompt_version: str = INCIDENT_PROMPT_VERSION

    def as_api(self, correlation_id: str) -> dict:
        return {
            "incidentId": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "summary": self.summary,
            "impact": self.impact,
            "timeline": [{"time": t, "event": e} for t, e in self.timeline],
            "suspectedCause": self.suspected_cause,
            "affectedServices": list(self.affected_services),
            "recommendedActions": list(self.recommended_actions),
            "runbooks": [{"id": r.id, "title": r.title, "link": r.link} for r in self.runbooks],
            "confidence": self.confidence,
            "requiresHumanApproval": self.requires_human_approval,
            "approvalReasons": list(self.approval_reasons),
            "openQuestions": list(self.open_questions),
            "correlationId": correlation_id,
        }


def _text(value, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _strings(value, limit: int | None = None) -> tuple[str, ...]:
    items = tuple(v.strip() for v in value if isinstance(v, str) and v.strip()) if isinstance(value, list) else ()
    return items[:limit] if limit else items


def _confidence(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return round(min(max(float(value), 0.0), 1.0), 2)


class IncidentSummarizer:
    def __init__(self, llm: ChatModel) -> None:
        self._llm = llm

    def summarize(self, incident_text: str, incident_id: str | None = None,
                  correlation_id: str = "-") -> IncidentSummary:
        text = (incident_text or "").strip()
        if len(text) < MIN_INCIDENT_CHARS:
            raise IncidentInputError(f"incidentText must be at least {MIN_INCIDENT_CHARS} characters")
        if len(text) > MAX_INCIDENT_CHARS:
            raise IncidentInputError(f"incidentText must be at most {MAX_INCIDENT_CHARS} characters")
        if incident_id is not None and not _INCIDENT_ID.match(incident_id):
            raise IncidentInputError("incidentId must look like INC-2026-0042")

        cleaned = redact(text)
        if cleaned.changed:
            log.warning("[%s] sensitive data removed from incident text before processing: %s",
                        correlation_id, ",".join(cleaned.redacted_types))

        reply = self._llm.complete_json(INCIDENT_SYSTEM_PROMPT,
                                        build_incident_user_message(cleaned.text, catalogue_for_prompt()),
                                        INCIDENT_RESPONSE_SCHEMA)
        data = reply.data

        severity = data.get("severity") if data.get("severity") in SEVERITIES else "UNKNOWN"
        timeline = tuple((_text(i.get("time"), "unknown"), _text(i.get("event")))
                         for i in data.get("timeline", []) if isinstance(i, dict) and _text(i.get("event")))
        cited = _strings(data.get("runbookIds"))
        runbooks = tuple(BY_ID[r] for r in dict.fromkeys(cited) if r in BY_ID)
        dropped = tuple(r for r in cited if r not in BY_ID)
        confidence = _confidence(data.get("confidence"))
        if dropped:
            log.warning("[%s] model recommended runbooks not in the catalogue; dropped: %s", correlation_id, dropped)

        reasons = []
        if confidence < APPROVAL_CONFIDENCE:
            reasons.append("LOW_CONFIDENCE")
        if severity == "SEV1":
            reasons.append("SEV1")
        if severity == "UNKNOWN":
            reasons.append("SEVERITY_UNKNOWN")
        if not runbooks:
            reasons.append("NO_RUNBOOK_MATCH")
        if dropped:
            reasons.append("INVENTED_RUNBOOK")
        if cleaned.changed:
            reasons.append("SENSITIVE_DATA_IN_LOG")

        result = IncidentSummary(
            incident_id=incident_id,
            title=_text(data.get("title"), "Untitled incident"),
            severity=severity,
            summary=_text(data.get("summary")),
            impact=_text(data.get("impact"), "unknown"),
            timeline=timeline,
            suspected_cause=_text(data.get("suspectedCause"), "unknown"),
            affected_services=_strings(data.get("affectedServices")),
            recommended_actions=_strings(data.get("recommendedActions"), MAX_ACTIONS),
            runbooks=runbooks,
            confidence=confidence,
            open_questions=_strings(data.get("openQuestions")),
            requires_human_approval=bool(reasons),
            approval_reasons=tuple(reasons),
            redacted_types=cleaned.redacted_types,
            dropped_runbook_ids=dropped,
            model=reply.model,
        )
        log.info("[%s] incident summarised: severity=%s confidence=%.2f approval=%s reasons=%s runbooks=%s "
                 "model=%s tokens=%s/%s", correlation_id, severity, confidence, result.requires_human_approval,
                 ",".join(reasons) or "-", [r.id for r in runbooks], reply.model, reply.input_tokens,
                 reply.output_tokens)
        return result
