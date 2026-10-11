# Database Setup & Migrations

This directory contains PostgreSQL DDL scripts, schema migrations, and synthetic seed datasets for the Mortgage Intelligence Platform[cite: 7, 8].


## Demo IDs (Core Reference)
| ID | Scenario / Status |
| --- | --- |
| `BOR-001` | Primary demo borrower (Jamie Nguyen) |
| `MTG-1001` | `ACTIVE`, on-time payments reference |
| `MTG-1002` | `DELINQUENT`, 45 days past due (DPD) |

## Connection Settings

Copy `.env.example` to configure local database environments:

```text
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mortgage_intel
POSTGRES_USER=mortgage_app
POSTGRES_PASSWORD=<set_locally>

