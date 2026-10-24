/**
 * M6 Task 6.4 demo: login -> token in memory -> GET mortgage -> GET servicing history -> token rejected (401)
 * -> automatic re-login + retry -> 403 is surfaced, not retried.
 *
 *   MORTGAGE_API_PASSWORD=... npm run demo
 */
import { loadConfig } from "./config.js";
import { ApiError, ConfigError } from "./errors.js";
import { createMortgageApiConsumer } from "./mortgageClient.js";

const MORTGAGE_ID = process.env.DEMO_MORTGAGE_ID ?? "MTG-1001";

const step = (title: string) => console.log(`\n== ${title} ==`);
const log = (event: string, details?: Record<string, unknown>) =>
  console.log(`   [client] ${event}${details ? " " + JSON.stringify(details) : ""}`);

async function main(): Promise<void> {
  const config = loadConfig();
  if (config.usesInsecureHttp) {
    console.warn("WARNING: plain HTTP on localhost (local dev only). Use https:// for any shared or deployed environment.");
  }
  const { session, client } = createMortgageApiConsumer(config, { logger: log });

  step(`1. Login as ${config.username} (token kept in memory only)`);
  await session.login();
  console.log(`   roles=${session.roles.join(",")} expiresIn=${Math.round(session.expiresInMs / 1000)}s session=${JSON.stringify(session)}`);

  step(`2. GET ${config.mortgageBaseUrl}/api/v1/mortgages/${MORTGAGE_ID} with Authorization: Bearer <token>`);
  const mortgage = await client.getMortgage(MORTGAGE_ID);
  console.log(`   ${mortgage.mortgageExternalId} borrower=${mortgage.borrowerExternalId} status=${mortgage.status} balance=${mortgage.outstandingBalance}`);

  step(`3. GET ${config.servicingBaseUrl}/api/v1/mortgages/${MORTGAGE_ID}/servicing-history (same token, other service)`);
  const history = await client.getServicingHistory(MORTGAGE_ID);
  console.log(`   ${history.events.length} event(s)`);
  for (const event of history.events.slice(-3)) {
    console.log(`   - ${event.eventTime} ${event.eventType}: ${event.description}`);
  }

  step("4. Token rejected (simulates expiry): server answers 401 -> client re-logs in and retries once");
  session.forceTokenRejectionForDemo();
  const again = await client.getMortgage(MORTGAGE_ID);
  console.log(`   retry succeeded: ${again.mortgageExternalId} status=${again.status}`);

  step("5. Restricted call with the same identity: POST /api/v1/mortgages -> 403 is surfaced, never retried");
  if (session.roles.some((role) => role === "ADMIN" || role === "UNDERWRITER")) {
    console.log(`   skipped: ${session.roles.join(",")} may create mortgages; run as servicing@ / risk@ / support@ to see the 403`);
  } else {
    try {
      await client.createMortgage({
        mortgageExternalId: "MTG-9998",
        borrowerExternalId: "BOR-001",
        originalAmount: 100000,
        outstandingBalance: 100000,
        originationDate: "2025-06-01",
      });
      throw new Error("expected 403 ACCESS_DENIED but the call succeeded");
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 403)) throw err;
      console.log(`   ${err.status} ${err.code}: ${err.message} (correlationId=${err.correlationId})`);
    }
  }

  session.clear();
  console.log("\nDone. The token was never printed or written to disk; session cleared.");
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError) {
    console.error(`Configuration error: ${err.message}`);
  } else if (err instanceof ApiError) {
    console.error(`API error: ${err.status} ${err.code}: ${err.message}${err.correlationId ? ` (correlationId=${err.correlationId})` : ""}`);
  } else {
    console.error(err);
  }
  process.exitCode = 1;
});
