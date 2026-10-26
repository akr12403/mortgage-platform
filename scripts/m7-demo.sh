#!/usr/bin/env bash
# M7 demo: follows the milestone's 4-step demo scenario against the running compose stack (~10 minutes).
#   bash scripts/m7-demo.sh             # run straight through
#   PAUSE=1 bash scripts/m7-demo.sh     # wait for Enter before each step (rehearsal / live demo)
#   BOTH_INCIDENTS=1 bash scripts/m7-demo.sh  # step 4 also summarises the well-evidenced DLQ incident
# Prereq: docker compose up --build -d (all healthy), knowledge base ingested (docker compose run --rm knowledge-ingest),
#         AUTH_SEED_PASSWORD and LLM_API_KEY in .env. Each run makes 2-3 LLM calls (well under 5 cents).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MS=${MORTGAGE_API_BASE:-http://localhost:8080}
KA=${ASSISTANT_API_BASE:-http://localhost:8001}
INCIDENTS=ai/mortgage-knowledge-assistant/incidents

env_value() { [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
SEED_PASSWORD="${AUTH_SEED_PASSWORD:-$(env_value AUTH_SEED_PASSWORD)}"
[[ -n "$SEED_PASSWORD" ]] || { echo "AUTH_SEED_PASSWORD is not set (export it or put it in .env)." >&2; exit 1; }

step() {
  printf '\n\033[1;36m== %s ==\033[0m\n' "$*"
  if [[ "${PAUSE:-0}" == "1" ]]; then read -r -p "   (Enter to run) " _; fi
}
say() { printf '   \033[2m%s\033[0m\n' "$*"; }

login() {  # login USERNAME -> access token on stdout (never printed by this script)
  local body
  body=$(SEED_PASSWORD="$SEED_PASSWORD" U="$1" python3 -c 'import json,os; print(json.dumps({"username":os.environ["U"],"password":os.environ["SEED_PASSWORD"]}))')
  curl -sS -X POST "$MS/api/v1/auth/login" -H 'Content-Type: application/json' -d "$body" \
    | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("accessToken",""))
except Exception: print("")'
}

ask() {  # ask TOKEN JSON_BODY -> pretty answer summary
  local tmp code
  tmp=$(mktemp)
  code=$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "$KA/api/v1/assistant/ask" \
    -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d "$2")
  printf '   POST /api/v1/assistant/ask -> HTTP %s\n' "$code"
  python3 - "$tmp" <<'PY'
import json, sys, textwrap
d = json.load(open(sys.argv[1]))
if "answer" not in d:
    print("   ", d); sys.exit(0)
print("   answer:")
for line in d["answer"].splitlines():
    print(textwrap.fill(line, 110, initial_indent="     ", subsequent_indent="       "))
if d["citations"]:
    for c in d["citations"]:
        print(f"   citation: {c['documentId']} / {c['section']} / {c['chunkId']}")
else:
    print("   citations: [] (none)")
print(f"   confidence: {d['confidence']}   requiresHumanApproval: {d['requiresHumanApproval']}   correlationId: {d['correlationId']}")
PY
  rm -f "$tmp"
}

incident() {  # incident TOKEN FILE ID -> summary
  local tmp code
  tmp=$(mktemp)
  code=$(python3 -c 'import json,sys; print(json.dumps({"incidentId":sys.argv[2],"incidentText":open(sys.argv[1]).read()}))' "$2" "$3" \
    | curl -sS -o "$tmp" -w '%{http_code}' -X POST "$KA/api/v1/assistant/summarize-incident" \
      -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d @-)
  printf '   POST /api/v1/assistant/summarize-incident (%s) -> HTTP %s\n' "$3" "$code"
  python3 - "$tmp" <<'PY'
import json, sys, textwrap
d = json.load(open(sys.argv[1]))
if "severity" not in d:
    print("   ", d); sys.exit(0)
w = lambda label, text: print(textwrap.fill(text, 110, initial_indent=f"   {label:<14}", subsequent_indent=" " * 17))
w("title:", d["title"]); w("severity:", d["severity"]); w("cause:", d["suspectedCause"])
for a in d["recommendedActions"][:3]:
    w("action:", a)
print(f"   runbooks:     {[r['link'] for r in d['runbooks']] or 'none matched'}")
print(f"   confidence:   {d['confidence']}")
flag = "\033[1;33m" if d["requiresHumanApproval"] else ""
print(f"   {flag}requiresHumanApproval: {d['requiresHumanApproval']}  reasons: {d['approvalReasons'] or '-'}\033[0m")
PY
  rm -f "$tmp"
}

printf '\033[1mM7 AI/RAG Mortgage Assistant demo\033[0m  (assistant: %s)\n' "$KA"
READY=$(curl -sS "$KA/health/ready" || true)
python3 - "$READY" <<'PY' || { echo "Assistant not ready. Run: docker compose up --build -d && docker compose run --rm knowledge-ingest" >&2; exit 1; }
import json, sys
d = json.loads(sys.argv[1] or "{}")
c = d.get("checks", {})
print(f"   /health/ready: {d.get('status')}  corpus {d.get('corpusVersion')}  chunks {c.get('knowledgeChunks')}  "
      f"database {c.get('database')}  AI provider configured {c.get('aiProviderConfigured')}")
sys.exit(0 if d.get("status") == "UP" else 1)
PY

TOKEN=$(login servicing@capstone.local)
[[ -n "$TOKEN" ]] || { echo "Login failed: AUTH_SEED_PASSWORD must match what mortgage-service seeded." >&2; exit 1; }
printf '   POST /ask with NO token -> HTTP %s (M6 JWT required)\n' \
  "$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$KA/api/v1/assistant/ask" -H 'Content-Type: application/json' -d '{"question":"x"}')"
say "Logged in as servicing@capstone.local (SERVICING_AGENT); the token is kept in memory and never printed."

# ------------------------------------------------------------------------------------------------------------------
step "1. Ask: \"What is the delinquency contact timeline?\" -> answer + citation  (3 min)"
say "Pipeline: redact PII -> embed (text-embedding-3-small) -> top-5 from pgvector -> gate at 0.45 -> gpt-6-luna with"
say "prompt ask-v1 (context only, strict JSON) -> cited chunk ids verified in code."
ask "$TOKEN" '{"question":"What is the delinquency contact timeline?"}'
say "The citation is a real row in pgvector:"
docker exec capstone-postgres psql -U "${POSTGRES_USER:-mortgage_app}" -d "${POSTGRES_DB:-mortgage_intel}" -At -F ' | ' -c \
  "SELECT chunk_id, doc_file, section, token_count FROM knowledge_chunk WHERE chunk_id = 'delinquency-playbook:v1:c-05';" \
  | sed 's/^/     /' || say "(psql not reachable; skip)"

# ------------------------------------------------------------------------------------------------------------------
step "2. Ask an unrelated question -> insufficient context  (2 min)"
say "Best match must reach the calibrated threshold (0.45): on-corpus 0.528-0.768 vs off-corpus 0.065-0.374."
ask "$TOKEN" '{"question":"What is the capital of France?"}'
say "No citation, confidence below the threshold, and the LLM was never called (no tokens spent)."
say "Near-domain check: \"What is today's 30-year fixed mortgage rate?\" (best 0.374, also rejected):"
ask "$TOKEN" '{"question":"What is today'"'"'s 30-year fixed mortgage rate?"}'

# ------------------------------------------------------------------------------------------------------------------
step "3. Prompt library entry: underwriting summary  (2 min)"
say "docs/ai/prompt-library.md: 6 versioned templates; ask-v1 and incident-summary-v1 drift-tested against the code."
SECTION=$(awk '/^## `underwriting-summary-v1`/{p=1} p&&/^---$/{exit} p' docs/ai/prompt-library.md)
printf '%s\n' "$SECTION" | awk '/^\*\*User message/{exit} {print}' | sed 's/^/     /'
printf '%s\n' "$SECTION" | grep -E '^\*\*(Example input|Expected output)' | fold -s -w 110 | sed 's/^/     /'
say "Guardrails: checklist with citations, UNKNOWN for missing facts, never approve/decline, no protected characteristics."
say "Human approval scenarios: docs/ai/governance.md#human-in-the-loop-when-a-person-must-decide"

# ------------------------------------------------------------------------------------------------------------------
step "4. Incident summarization with the approval flag  (3 min)"
ADMIN_TOKEN=$(login admin@capstone.local)
[[ -n "$ADMIN_TOKEN" ]] || { echo "Admin login failed." >&2; exit 1; }
say "ADMIN only. Prompt incident-summary-v1; runbooks only from the fixed catalogue; approval decided in code."
printf '   servicing@ (not ADMIN) -> HTTP %s\n' "$(python3 -c 'import json; print(json.dumps({"incidentText":"x"*40}))' \
  | curl -sS -o /dev/null -w '%{http_code}' -X POST "$KA/api/v1/assistant/summarize-incident" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d @-)"
incident "$ADMIN_TOKEN" "$INCIDENTS/INC-2026-0043-vague-report.txt" INC-2026-0043
say "Vague, second-hand report: low confidence, unknown severity, no runbook -> a person must confirm before acting."
if [[ "${BOTH_INCIDENTS:-0}" == "1" ]]; then
  incident "$ADMIN_TOKEN" "$INCIDENTS/INC-2026-0042-servicing-dlq-backlog.txt" INC-2026-0042
  say "Well-evidenced DLQ backlog: SEV2, cause found, messaging-dlq runbook, high confidence -> no flag."
fi
say "Audit line (no incident text, no question text):"
docker logs knowledge-assistant 2>&1 | grep -E " (ask|incident) user=" | tail -2 \
  | sed -E 's/^.*\] (ask|incident) /\1 /; s/ model=.*$//' | fold -s -w 110 | sed 's/^/     /' || true

printf '\n\033[1;32mDemo complete.\033[0m Evidence index: docs/operations/m7-demo-checklist.md\n'
