// J4: authentication (401) and role-based authorization (403 ACCESS_DENIED). Writes are only sent as users that
// must be denied, so a passing run changes no data.
import { Then, When } from "@cucumber/cucumber";
import assert from "node:assert/strict";
import { borrowerRequest, isoDate, pick } from "../support/data.mjs";

When("I record the underwriting decision {string} for mortgage {string}", async function (decision, mortgageId) {
  this.last = await this.mortgages.decide(await this.token(), mortgageId, decision);
});

Then("mortgage {string} should still be {string}", async function (mortgageId, status) {
  const response = await this.mortgages.get(await this.token(), mortgageId);
  assert.equal(response.status, 200, this.describe(response));
  assert.equal(response.body.status, status, this.describe(response));
});

// Valid request bodies, so a 403 can only come from the role check and not from validation.
const ACTIONS = {
  "register a borrower": (w, token) => w.borrowers.create(token, borrowerRequest(pick.borrowerId())),
  "post a payment to MTG-1001": (w, token) => w.mortgages.postPayment(token, "MTG-1001",
    { dueDate: isoDate(-2), paidDate: isoDate(0), amount: 1.0, status: "POSTED" }),
  "run the delinquency evaluation": (w, token) => w.mortgages.runDelinquencyEvaluation(token),
  "read the borrower BOR-001": (w, token) => w.borrowers.get(token, "BOR-001"),
};

When(/^I try to (.+)$/, async function (action) {
  const call = ACTIONS[action];
  assert.ok(call, `unknown action "${action}"; known: ${Object.keys(ACTIONS).join(", ")}`);
  this.last = await call(this, await this.token());
});

When(/^I read the borrower "([^"]+)" with (no token|a tampered token)$/, async function (borrowerId, credentials) {
  let token;
  if (credentials === "a tampered token") {
    // A real token with one character of the payload changed: the signature no longer matches.
    const [header, payload, signature] = (await this.auth.tokenFor("admin@capstone.local")).split(".");
    const flipped = payload.slice(0, -1) + (payload.endsWith("A") ? "B" : "A");
    token = [header, flipped, signature].join(".");
  }
  this.last = await this.borrowers.get(token, borrowerId);
});
