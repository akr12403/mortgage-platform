// Steps shared by several journeys: who is acting, response checks, and the servicing-history check that proves an
// event reached servicing-service.
import { Given, Then } from "@cucumber/cucumber";
import assert from "node:assert/strict";
import { eventuallyTimeout } from "../support/timeouts.mjs";
import { borrowerRequest, createWithFreshId, eventually, mortgageRequest, pick } from "../support/data.mjs";

Given("I am logged in as {string}", async function (username) {
  this.username = username;
  await this.token(username);
});

Given("an active mortgage created for this scenario", async function () {
  // Set-up through the API as the underwriter (as J1 does), with the loan approved at creation: status ACTIVE.
  const token = await this.token("underwriter@capstone.local");
  const borrower = await createWithFreshId(() => this.borrowers.create(token, borrowerRequest(pick.borrowerId())));
  assert.equal(borrower.status, 201, `borrower set-up failed: ${this.describe(borrower)}`);
  this.borrowerId = borrower.body.borrowerExternalId;
  const mortgage = await createWithFreshId(() =>
    this.mortgages.create(token, mortgageRequest(this.borrowerId, { amount: 300000, decision: "APPROVED" })));
  assert.equal(mortgage.status, 201, `mortgage set-up failed: ${this.describe(mortgage)}`);
  assert.equal(mortgage.body.status, "ACTIVE", `set-up mortgage is not ACTIVE: ${this.describe(mortgage)}`);
  this.mortgageId = mortgage.body.mortgageExternalId;
  this.balanceBefore = Number(mortgage.body.outstandingBalance);
});

Then("the response status should be {int}", function (status) {
  assert.equal(this.last?.status, status, this.describe());
});

Then("the error code should be {string}", function (code) {
  assert.equal(this.last?.body?.code, code, this.describe());
  assert.ok(this.last.body.correlationId, `error envelope without correlationId: ${this.describe()}`);
});

Then("the response header {string} should be {string}", function (name, value) {
  assert.equal(this.last?.headers?.[name.toLowerCase()], value, this.describe());
});

Then("the mortgage status should be {string}", async function (status) {
  const response = await this.mortgages.get(await this.token(), this.mortgageId);
  assert.equal(response.status, 200, this.describe(response));
  assert.equal(response.body.status, status, this.describe(response));
});

async function historyTypes(world) {
  const response = await world.servicing.history(await world.token(), world.mortgageId);
  // 404 until servicing-service has consumed the mortgage's first event.
  return response.status === 200 ? response.body.events.map((event) => event.eventType) : [];
}

Then("the servicing history eventually shows {string}", async function (type) {
  const types = await eventually(() => historyTypes(this), (t) => t.includes(type), eventuallyTimeout());
  assert.ok(types.includes(type), `${type} not in the servicing history of ${this.mortgageId} after ` +
    `${eventuallyTimeout().timeoutMs / 1000} s: [${types}] (correlationId ${this.correlationId})`);
});

Then("the servicing history eventually shows {string} and {string}", async function (first, second) {
  const done = (t) => t.includes(first) && t.includes(second);
  const types = await eventually(() => historyTypes(this), done, eventuallyTimeout());
  assert.ok(done(types), `${first} and ${second} not both in the servicing history of ${this.mortgageId}: ` +
    `[${types}] (correlationId ${this.correlationId})`);
});

Then("the servicing history eventually shows {string} exactly once", async function (type) {
  const count = (t) => t.filter((x) => x === type).length;
  await eventually(() => historyTypes(this), (t) => count(t) >= 1, eventuallyTimeout());
  await new Promise((resolve) => setTimeout(resolve, 5_000)); // time for a duplicate, if any, to arrive
  const types = await historyTypes(this);
  assert.equal(count(types), 1, `expected one ${type} for ${this.mortgageId}: [${types}]`);
});
