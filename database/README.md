# Database Setup & Migrations

This directory contains PostgreSQL DDL scripts, schema migrations, and synthetic seed datasets for the Mortgage Intelligence Platform[cite: 7, 8].

## Connection Settings

Copy `.env.example` to configure local database environments:

```text
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mortgage_intel
POSTGRES_USER=mortgage_app
POSTGRES_PASSWORD=<set_locally>