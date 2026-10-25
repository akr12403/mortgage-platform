"""The fixed catalogue of runbook sections the incident summarizer may recommend (M7 Task 7.6).

The model only chooses ids from this list; ids it invents are dropped in code and flag the summary for human
review. Every link points at a real heading in docs/operations/ or docs/ai/ (checked by tests/test_incident.py).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Runbook:
    id: str
    title: str
    link: str   # repository path + GitHub heading anchor
    use_when: str


CATALOGUE: tuple[Runbook, ...] = (
    Runbook("messaging-dlq", "Messaging: messages in a DLQ",
            "docs/operations/messaging-runbook.md#incident-messages-in-a-dlq",
            "messages in a dead-letter queue; consumer failures after 3 receives; poison or malformed events"),
    Runbook("messaging-everyday-checks", "Messaging: everyday checks",
            "docs/operations/messaging-runbook.md#everyday-checks",
            "queue depth, consumer lag, checking SNS/SQS health"),
    Runbook("messaging-troubleshooting", "Messaging: troubleshooting",
            "docs/operations/messaging-runbook.md#troubleshooting",
            "LocalStack/SQS connectivity, subscriptions, consumers not receiving"),
    Runbook("secrets-jwt-rotation", "Rotate the JWT signing key",
            "docs/operations/runbook.md#jwt-signing-key-jwt_secret",
            "JWT secret exposed or suspected; mass 401 INVALID_TOKEN after a key change"),
    Runbook("secrets-db-password-rotation", "Rotate the database password",
            "docs/operations/runbook.md#database-password-postgres_password",
            "database credential exposed; services failing to authenticate to PostgreSQL"),
    Runbook("secret-committed-to-git", "If a secret was committed to Git",
            "docs/operations/runbook.md#if-a-secret-was-committed-to-git",
            "a secret found in the repository or a failed secret-detection gate"),
    Runbook("secrets-verify-after-rotation", "Verify after any rotation",
            "docs/operations/runbook.md#verify-after-any-rotation",
            "checks to run after rotating any secret"),
    Runbook("security-gates-troubleshooting", "Security gates: troubleshooting",
            "docs/operations/devsecops-baseline.md#troubleshooting",
            "CI security gate failures: gitleaks, semgrep, trivy, pip-audit"),
    Runbook("ai-api-key", "AI provider API key",
            "docs/ai/governance.md#api-key-and-provider",
            "OpenAI key leaked, quota exhausted, 401/429 from the AI provider"),
)

BY_ID = {r.id: r for r in CATALOGUE}


def catalogue_for_prompt() -> str:
    return "\n".join(f'<runbook id="{r.id}" title="{r.title}">use when: {r.use_when}</runbook>' for r in CATALOGUE)
