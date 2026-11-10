// J1: borrower -> mortgage onboarding, with the underwriting decision (the approval workflow).
import { Then, When } from "@cucumber/cucumber";
import assert from "node:assert/strict";
import { borrowerRequest, createWithFreshId, mortgageRequest, pick } from "../support/data.mjs";

When("I register a new borrower", async function () {
  const token = await this.token();
  this.last = await createWithFreshId(() => this.borrowers.create(token, borrowerRequest(pick.borrowerId())));
  this.borrowerId = this.last.body?.borrowerExternalId ?? null;
});

When("I register a borrower with the existing ID {string}", async function (borrowerId) {
  this.last = await this.borrowers.create(await this.token(), borrowerRequest(borrowerId));
});

Then("the new borrower can be retrieved by its business ID", async function () {
  const response = await this.borrowers.get(await this.token(), this.borrowerId);
  assert.equal(response.status, 200, this.describe(response));
  assert.equal(response.body.borrowerExternalId, this.borrowerId, this.describe(response));
});

When("I create a mortgage of {float} for the new borrower with a pending loan", async function (amount) {
  const token = await this.token();
  this.last = await createWithFreshId(() =>
    this.mortgages.create(token, mortgageRequest(this.borrowerId, { amount, decision: "PENDING" })));
  this.mortgageId = this.last.body?.mortgageExternalId ?? null;
  if (this.last.status === 201) {
    assert.equal(this.last.body.borrowerExternalId, this.borrowerId, this.describe());
    assert.equal(this.last.body.loan?.underwritingDecision, "PENDING", this.describe());
  }
});

When("I record the underwriting decision {string} for the new mortgage", async function (decision) {
  this.last = await this.mortgages.decide(await this.token(), this.mortgageId, decision);
});
