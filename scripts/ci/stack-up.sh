#!/usr/bin/env bash
# Shared by scripts/ci/integration-tests.sh and scripts/ci/e2e-tests.sh (sourced, not run): start the compose stack
# from the pipeline's images (or, with LOCAL_IMAGES=1, the images docker compose built) and wait until every service
# is healthy. Expects ROOT and cwd = repo root. Honors COMPOSE_FILE (the E2E run adds tests/e2e/docker-compose.e2e.yml).
# In CI it also writes a throwaway .env (random JWT secret, DB and seed passwords) that exists only on the runner.
SERVICES="mortgage-service servicing-service analytics-service knowledge-assistant"

if [ "${LOCAL_IMAGES:-0}" != "1" ]; then
  : "${IMAGE_TAG:?IMAGE_TAG (e.g. sha-<commit>) is required}"
  prefix="${IMAGE_PREFIX:-ghcr.io/${GITHUB_REPOSITORY:?}}"
  prefix="$(printf '%s' "$prefix" | tr '[:upper:]' '[:lower:]')"
  for s in $SERVICES; do
    docker pull -q "$prefix/$s:$IMAGE_TAG"
    docker tag "$prefix/$s:$IMAGE_TAG" "capstone/$s:dev"     # the names docker-compose.yml runs
  done

  # Throwaway secrets for this run only (CI). A developer's real .env is never touched locally.
  rnd() { python3 -c 'import secrets; print(secrets.token_urlsafe(int(__import__("sys").argv[1])))' "$1"; }
  cp .env.example .env
  python3 - "$(rnd 48)" "$(rnd 18)" "$(rnd 18)" <<'PY'
import re, sys
jwt, db, seed = sys.argv[1:]
text = open(".env").read()
for key, value in (("JWT_SECRET", jwt), ("POSTGRES_PASSWORD", db), ("AUTH_SEED_PASSWORD", seed)):
    text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
open(".env", "w").write(text)
PY
fi
export AUTH_SEED_PASSWORD="$(grep -E '^AUTH_SEED_PASSWORD=' .env | cut -d= -f2-)"
[ -n "$AUTH_SEED_PASSWORD" ] || { echo "AUTH_SEED_PASSWORD missing in .env" >&2; exit 1; }

printf '\n\033[1;36m== Start the stack (no build: pipeline images) ==\033[0m\n'
docker compose up -d --no-build
# Wait on the services' own health endpoints (one-shot containers such as db-migrate exit by design).
for url in http://localhost:8080/actuator/health http://localhost:8081/actuator/health \
           http://localhost:8000/health http://localhost:8001/health; do
  for i in $(seq 1 60); do
    curl -fsS -o /dev/null "$url" 2>/dev/null && { echo "  healthy: $url"; break; }
    [ "$i" = 60 ] && { echo "  NOT healthy after 5 min: $url" >&2; docker compose ps; exit 1; }
    sleep 5
  done
done
docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'
