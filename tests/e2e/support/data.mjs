// Test data for the journeys. Every scenario creates its own borrower and mortgage, so scenarios don't depend on
// each other and can run in parallel or be re-run. Business IDs have fixed formats (BOR-###, MTG-####, LOAN-####),
// so new IDs come from ranges the seed data doesn't use, and a create that hits an existing ID (409) is retried
// with another one.
import { randomInt } from "node:crypto";

export const pick = {
  borrowerId: () => `BOR-${randomInt(500, 1000)}`,
  mortgageId: () => `MTG-${randomInt(5000, 10000)}`,
  loanId: () => `LOAN-${randomInt(5000, 10000)}`,
};

export function isoDate(daysFromToday = 0) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + daysFromToday);
  return date.toISOString().slice(0, 10);
}

export function borrowerRequest(borrowerId) {
  const n = borrowerId.slice(4);
  return {
    borrowerExternalId: borrowerId,
    firstName: "E2E",
    lastName: `Borrower${n}`,
    email: `e2e.borrower${n}.${Date.now()}@example.test`,
    phone: "+1-555-0199",
    dateOfBirth: "1990-01-15",
  };
}

export function mortgageRequest(borrowerId, { amount = 320000, decision = "PENDING", rate = 0.065, termMonths = 360 } = {}) {
  return {
    mortgageExternalId: pick.mortgageId(),
    borrowerExternalId: borrowerId,
    originalAmount: amount,
    outstandingBalance: amount,
    originationDate: isoDate(-400),
    loan: { loanExternalId: pick.loanId(), interestRate: rate, termMonths, underwritingDecision: decision },
  };
}

/** Calls `create(attempt)` until it doesn't return 409 (ID already taken), at most `tries` times. */
export async function createWithFreshId(create, tries = 8) {
  let response;
  for (let attempt = 0; attempt < tries; attempt += 1) {
    response = await create(attempt);
    if (response.status !== 409) return response;
  }
  return response;
}

/** Polls `read` until `done(value)` is true or the timeout passes; returns the last value either way. */
export async function eventually(read, done, { timeoutMs = 60_000, intervalMs = 2_000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let value = await read();
  while (!done(value) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    value = await read();
  }
  return value;
}
