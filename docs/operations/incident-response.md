# Incident Response (M9 Task 9.4)

How the team detects, triages, escalates, fixes and learns from incidents on the Mortgage Intelligence Platform. Alert-specific steps are in the [runbook](runbook.md#alerts), the targets in [slo.md](slo.md), and the log and search reference in [observability.md](observability.md).

## Severity

| Severity | Examples | Response | Update cadence |
| --- | --- | --- | --- |
| **SEV-1** | Payments can't be posted or are posted wrongly; borrower data exposed; every service down | Immediately, all hands; incident commander named | every 30 min |
| **SEV-2** | A payment SLO alert is firing but some payments succeed; one service down; events dead-lettering | Within 15 min | every hour |
| **SEV-3** | Degraded but within SLO: slow analytics, assistant unavailable, a non-critical job failed | Same working day | at resolution |

When in doubt, choose the higher severity; downgrading later is cheap. **Any suspected data exposure is SEV-1** and also follows the security steps: [runbook key compromise](runbook.md#jwt-signing-key-jwt_secret) and the [risk register](../security/risk-register.md).

## Roles

| Role | Does | Who (capstone team) |
| --- | --- | --- |
| **Incident commander (IC)** | Owns the incident, decides, keeps the timeline, declares it resolved | the on-call platform lead |
| **Investigator** | Triage in Splunk, applies the fix or rollback | the on-call engineer for the failing service ([ownership](../architecture/service-ownership-matrix.md)) |
| **Communicator** | Status updates to stakeholders (servicing operations, risk) | the IC, unless SEV-1 |

In a team of one, the same person holds all three roles but still writes the timeline as they go.

## Lifecycle

```text
detect -> triage -> (escalate) -> mitigate -> recover -> verify -> close -> RCA
```

1. **Detect.** A Splunk alert (*Activity → Triggered Alerts*, or the alert's action), a user report or the dashboard. Note the time: it's the first line of the timeline.
2. **Triage (target: within 15 minutes of detection).**
   - Open the dashboard *Mortgage Platform: Service Health*. Which services are affected, since when, and how many requests?
   - From *Latest errors*, follow one failing request by its `correlationId` across services:
     ```text
     index=mortgage_dev correlationId="<id>" | sort _time
     ```
   - Group the errors to find the cause:
     ```text
     index=mortgage_dev log.level=ERROR earliest=-30m | stats count, min(_time) as first by service.name, error.type
     ```
   - Set the severity. Open the incident record (below).
3. **Escalate** if:
   - it's SEV-1;
   - the cause isn't known after 15 minutes (SEV-2) or 30 minutes (SEV-3);
   - the fix needs someone else's access, such as AWS break-glass or a database restore.

   Escalate to the next owner in the [service ownership matrix](../architecture/service-ownership-matrix.md), then to the instructor or platform owner.
4. **Mitigate.** Stop the harm first and find the root cause later:
   - [roll back](runbook.md#rollback);
   - restart or restore a dependency;
   - pause a consumer.

   Don't change AWS resources in the console: drift is detected and undone ([terraform-drift-exercise.md](terraform-drift-exercise.md#remediation-choices)).
5. **Recover and verify:**
   - the alert clears;
   - the payment SLI tile is green again;
   - a test request succeeds end to end (`python3 tests/integration/test_stack_smoke.py`, or a `correlationId` search);
   - the DLQs are empty, or their messages have been redriven ([messaging-runbook.md](messaging-runbook.md)).
6. **Close.** The IC records the end time, the impact (failed requests, duration, SLO error budget used) and the follow-ups.
7. **RCA:** for every SEV-1 and SEV-2, within 2 working days, as `docs/operations/rca-<yyyy-mm-dd>.md`. The sections are below. It's blameless: it describes what the system and the process allowed, not who made a mistake.

## Incident record (kept during the incident)

```text
Incident:     <short title>                 Severity: SEV-<n>      IC: <name>
Detected:     <UTC time> by <alert / report>
Impact:       <who/what is affected, since when>
Timeline:     <UTC time>  <what was seen / done / decided>   (one line per step)
Status:       investigating | mitigated | resolved
Follow-ups:   <items for the RCA>
```

Use UTC everywhere, so times match Splunk. Never paste secrets, tokens or borrower data into the record; refer to requests by `correlationId`.

## RCA template (`docs/operations/rca-<yyyy-mm-dd>.md`)

1. **Summary**, one paragraph: what happened, the impact, the cause, the fix.
2. **Impact:** users or operations affected, duration, failed requests, whether an SLI breached, and the error budget used.
3. **Timeline:** UTC timestamps from detection to close, with Splunk evidence.
4. **Root cause:** the technical cause, plus contributing factors (why it wasn't prevented, or was detected late).
5. **Corrective actions:** fix what broke, with owners and dates.
6. **Preventive actions:** monitoring, tests and runbook updates that stop it happening again or catch it sooner.

The AI incident summarizer (M7, `POST /api/v1/assistant/summarize-incident`) can draft a summary with runbook links from the incident record. The IC reviews and corrects it before it goes into the RCA.

## Exercises

| Date | Exercise | Result |
| --- | --- | --- |
| 2026-11-10 | PostgreSQL outage under traffic (`scripts/incident/db_outage_drill.py`) | Detected in 1 min 4 s (*Error spike*), payment SLO alerts at 3 min 3 s; root cause found from one correlationId trace; recovered 1 s after the database restart; 30 payments failed. [RCA](rca-2026-11-10.md) |
