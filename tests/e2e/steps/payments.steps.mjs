// J2 and J3: posting payments (posted or failed) against the scenario's mortgage.
import { Then, When } from "@cucumber/cucumber";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { isoDate } from "../support/data.mjs";

When("I post a {string} payment of {float} due {int} days ago", async function (status, amount, daysAgo) {
  const payment = { dueDate: isoDate(-daysAgo), amount, status };
  if (status === "POSTED") payment.paidDate = isoDate(0);
  const idempotencyKey = `e2e-${randomUUID()}`;
  this.lastPayment = { body: payment, idempotencyKey };
  this.last = await this.mortgages.postPayment(await this.token(), this.mortgageId, payment, idempotencyKey);
  if (this.last.status === 200) assert.equal(this.last.body.status, status, this.describe());
});

When("I send the same payment again with the same Idempotency-Key", async function () {
  const { body, idempotencyKey } = this.lastPayment;
  this.last = await this.mortgages.postPayment(await this.token(), this.mortgageId, body, idempotencyKey);
});

Then("the outstanding balance should have gone down by {float}", async function (amount) {
  const response = await this.mortgages.get(await this.token(), this.mortgageId);
  assert.equal(response.status, 200, this.describe(response));
  const expected = Math.round((this.balanceBefore - amount) * 100) / 100;
  assert.equal(Number(response.body.outstandingBalance), expected,
    `balance ${response.body.outstandingBalance}, expected ${this.balanceBefore} - ${amount} = ${expected}`);
});

Then("the payment should be listed for the mortgage", async function () {
  const response = await this.mortgages.listPayments(await this.token(), this.mortgageId);
  assert.equal(response.status, 200, this.describe(response));
  const { dueDate, amount } = this.lastPayment.body;
  const found = response.body.some((p) => p.dueDate === dueDate && Number(p.amount) === amount && p.status === "POSTED");
  assert.ok(found, `payment due ${dueDate} for ${amount} not listed: ${JSON.stringify(response.body)}`);
});
