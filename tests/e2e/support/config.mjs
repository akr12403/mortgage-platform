// Where the services are and how to log in. Defaults match docker-compose.yml on localhost; override with the same
// variables the other test suites use (MORTGAGE_API_BASE, ...). The seed password comes from AUTH_SEED_PASSWORD or
// the repo-root .env, never from this repository.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const env = process.env;

export const urls = {
  mortgage: env.MORTGAGE_API_BASE ?? "http://localhost:8080",
  servicing: env.SERVICING_API_BASE ?? "http://localhost:8081",
  analytics: env.ANALYTICS_API_BASE ?? "http://localhost:8000",
  assistant: env.ASSISTANT_API_BASE ?? "http://localhost:8001",
};

// How long to wait for an event to travel mortgage-service -> SNS -> SQS -> consumer.
export const eventTimeoutMs = Number(env.E2E_EVENT_TIMEOUT_MS ?? 60_000);
// The assistant's similarity gate (RAG_SIMILARITY_THRESHOLD in docker-compose.yml).
export const similarityThreshold = Number(env.RAG_SIMILARITY_THRESHOLD ?? 0.45);

export function seedPassword() {
  if (env.AUTH_SEED_PASSWORD) return env.AUTH_SEED_PASSWORD;
  const dotenv = fileURLToPath(new URL("../../../.env", import.meta.url));
  if (existsSync(dotenv)) {
    for (const line of readFileSync(dotenv, "utf8").split(/\r?\n/)) {
      if (line.startsWith("AUTH_SEED_PASSWORD=") && line.slice(19).trim()) return line.slice(19).trim();
    }
  }
  throw new Error("AUTH_SEED_PASSWORD is not set (environment or repo-root .env)");
}
