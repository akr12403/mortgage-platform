"""Bulk-load CapstoneMortgageLookup-dev from PostgreSQL (M8 Task 8.4).

    python -m src.services.lookup_load            # inside the analytics image; scripts/aws/lookup-load.sh runs it
                                                  # with mortgage-analytics-role credentials

Reads business IDs, status and amounts only (no borrower names or contact data) and writes one item per mortgage.
Prints a JSON summary; exit code 1 if the counts do not match.
"""
import json
import sys

from sqlalchemy import text

from src.services.lookup_service import MortgageLookupStore

QUERY = text("""
    SELECT m.mortgage_external_id, b.borrower_external_id, m.status,
           m.outstanding_balance, m.original_amount, m.origination_date
    FROM mortgage m
    JOIN borrower b ON b.id = m.borrower_id
    ORDER BY m.mortgage_external_id
""")


def main() -> int:
    from src.api.dependencies import SessionLocal

    store = MortgageLookupStore()
    if not store.configured:
        print("DYNAMODB_LOOKUP_TABLE is not set", file=sys.stderr)
        return 2
    with SessionLocal() as session:
        rows = [dict(row._mapping) for row in session.execute(QUERY)]
    written = store.bulk_load(rows)
    total_balance = sum(float(r["outstanding_balance"]) for r in rows)
    print(json.dumps({"table": store.table, "postgresRows": len(rows), "itemsWritten": written,
                      "outstandingBalanceTotal": round(total_balance, 2)}))
    return 0 if written == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
