#!/usr/bin/env bash
# M10 Task 10.4 backup/recovery check on the local stack: take a logical backup of the platform database, restore
# it into a scratch database, compare the row count of every table, then drop the scratch database and delete the
# backup file. The real database is only read.
#   bash scripts/ops/backup-restore-check.sh
# Report: reports/backup/<date>/backup-restore-check.md (git-ignored). In AWS the equivalent is an RDS snapshot
# restore (docs/operations/production-readiness.md, Backup and recovery).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
C="${PG_CONTAINER:-capstone-postgres}"
OUT="reports/backup/$(date -u +%F)"; mkdir -p "$OUT"
SCRATCH="restore_check_$(date -u +%Y%m%d%H%M%S)"
DUMP="$OUT/backup.dump"

# psql/pg_dump/pg_restore inside the container, as its superuser over the local socket (no password on this host).
pg() { docker exec -i "$C" sh -c "$1"; }
q()  { pg "psql -v ON_ERROR_STOP=1 -At -U \"\$POSTGRES_USER\" -d $1 -c \"$2\""; }
cleanup() { pg "dropdb -U \"\$POSTGRES_USER\" --if-exists $SCRATCH" >/dev/null 2>&1 || true; rm -f "$DUMP"; }
trap cleanup EXIT

db="$(pg 'printf %s "$POSTGRES_DB"')"
tables="$(q "$db" "select tablename from pg_tables where schemaname = 'public' order by 1")"

printf '== Backup (%s, pg_dump custom format) ==\n' "$db"
t0=$(date +%s)
pg 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DUMP"
t1=$(date +%s)
size=$(wc -c < "$DUMP" | tr -d ' ')
echo "  $size bytes in $((t1 - t0)) s"

printf '== Restore into %s ==\n' "$SCRATCH"
pg "createdb -U \"\$POSTGRES_USER\" $SCRATCH"
pg "pg_restore -U \"\$POSTGRES_USER\" -d $SCRATCH --no-owner --exit-on-error" < "$DUMP"
t2=$(date +%s)
echo "  restored in $((t2 - t1)) s"

printf '== Compare row counts ==\n'
report="$OUT/backup-restore-check.md"
{
  echo "Backup/restore check $(date -u +%FT%TZ): database \`$db\`, dump $size bytes in $((t1 - t0)) s, restore in $((t2 - t1)) s"
  echo
  echo "| Table | Rows (live) | Rows (restored) | Match |"
  echo "| --- | --- | --- | --- |"
} > "$report"
mismatch=0
for t in $tables; do
  live=$(q "$db" "select count(*) from public.\\\"$t\\\"")
  restored=$(q "$SCRATCH" "select count(*) from public.\\\"$t\\\"")
  ok=yes; [ "$live" = "$restored" ] || { ok=NO; mismatch=1; }
  echo "| $t | $live | $restored | $ok |" >> "$report"
done
cat "$report"
if [ "$mismatch" = 0 ]; then
  echo "Result: every table restored with the same row count." | tee -a "$report"
else
  echo "Result: row counts differ (writes during the check can cause this; re-run with the stack idle)." | tee -a "$report"
  exit 1
fi
