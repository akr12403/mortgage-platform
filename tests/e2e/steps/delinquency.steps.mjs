// J3: the delinquency snapshot that servicing-service builds from LoanDelinquent events.
import { Then, When } from "@cucumber/cucumber";
import assert from "node:assert/strict";
import { eventually } from "../support/data.mjs";
import { eventuallyTimeout } from "../support/timeouts.mjs";

const SEVERITIES = ["MODERATE", "SEVERE", "CRITICAL"];

When("I request the delinquency status of mortgage {string}", async function (mortgageId) {
  this.mortgageId = mortgageId;
  this.last = await this.servicing.delinquency(await this.token(), mortgageId);
});

Then("the delinquency status should be {string} with at least {int} days past due and a severity",
  function (status, minDays) {
    const body = this.last.body;
    assert.equal(body.status, status, this.describe());
    assert.ok(body.daysPastDue >= minDays, `daysPastDue ${body.daysPastDue} < ${minDays}: ${this.describe()}`);
    assert.ok(SEVERITIES.includes(body.severity), `unexpected severity: ${this.describe()}`);
    assert.ok(body.delinquentSince, `no delinquentSince: ${this.describe()}`);
  });

Then("the delinquency status eventually shows {string} with severity {string}", async function (status, severity) {
  const token = await this.token();
  const response = await eventually(
    () => this.servicing.delinquency(token, this.mortgageId),
    (r) => r.status === 200 && r.body.status === status && r.body.severity === severity,
    eventuallyTimeout());
  assert.equal(response.status, 200, this.describe(response));
  assert.equal(response.body.status, status, this.describe(response));
  assert.equal(response.body.severity, severity, this.describe(response));
  assert.ok(response.body.daysPastDue >= 30, this.describe(response));
});
