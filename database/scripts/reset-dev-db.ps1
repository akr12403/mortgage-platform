# reset-dev-db.ps1
# Resets the local PostgreSQL database, runs core migrations, and applies seed data.

Write-Host "=== Resetting Development Database ===" -ForegroundColor Cyan

$Env:PGPASSWORD = "change_me_locally"
$DB_USER = "mortgage_app"
$DB_NAME = "mortgage_intel"
$DB_HOST = "localhost"

Write-Host "Dropping and recreating database '$DB_NAME'..." -ForegroundColor Yellow
psql -U postgres -h $DB_HOST -c "DROP DATABASE IF EXISTS $DB_NAME;"
psql -U postgres -h $DB_HOST -c "CREATE DATABASE $DB_NAME;"

Write-Host "Configuring schema extensions and privileges..." -ForegroundColor Yellow
psql -U postgres -h $DB_HOST -d $DB_NAME -c 'CREATE EXTENSION IF NOT EXISTS "pgcrypto";'
psql -U postgres -h $DB_HOST -d $DB_NAME -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
psql -U postgres -h $DB_HOST -d $DB_NAME -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;"

Write-Host "Applying core DDL migration..." -ForegroundColor Yellow
psql -U $DB_USER -h $DB_HOST -d $DB_NAME -f "database/migrations/001_core_schema.sql"

Write-Host "Loading synthetic seed data..." -ForegroundColor Yellow
psql -U $DB_USER -h $DB_HOST -d $DB_NAME -f "database/seed/seed_mortgage_data.sql"

Write-Host "=== Database Reset & Seed Completed Successfully! ===" -ForegroundColor Green