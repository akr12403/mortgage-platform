#!/usr/bin/env bash
# Markdown summary of a terraform plan/apply log for $GITHUB_STEP_SUMMARY (account ids redacted).
#   bash scripts/ci/plan-summary.sh "<title>" <log file> <terraform exit code> >> "$GITHUB_STEP_SUMMARY"
# Exit codes (plan -detailed-exitcode): 0 no changes, 1 error, 2 changes.
set -uo pipefail
title="$1"; log="$2"; rc="${3:-0}"
redact() { sed -E 's/[0-9]{12}/<account>/g; s/\x1b\[[0-9;]*m//g'; }
case "$rc" in
  0) verdict="✅ no changes" ;;
  2) verdict="⚠️ changes" ;;
  *) verdict="❌ error (exit $rc)" ;;
esac
echo "### $title: $verdict"
echo
grep -E '^(Plan:|Apply complete!|No changes\.)' "$log" | redact | sed 's/^/**/; s/$/**/' || true
echo
changes="$(grep -E '^  # .* (will be|must be)' "$log" | redact | sed -E 's/^  # /- `/; s/ (will be|must be)/` \1/' | head -60)"
[ -n "$changes" ] && { echo "$changes"; echo; }
grep -qE '^│ Error|^Error' "$log" && { echo '```text'; grep -E -A6 '^│ Error|^Error' "$log" | redact | head -40; echo '```'; echo; }
echo "<details><summary>Full output</summary>"
echo
echo '```text'
redact < "$log" | tail -c 60000
echo '```'
echo "</details>"
