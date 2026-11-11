// Per-scenario state and the hooks around it. Each scenario gets its own Playwright API context with a correlation ID
// (X-Correlation-Id: e2e-<uuid>) that every service logs, so a failed scenario can be traced in Splunk with
// `index=mortgage_dev correlationId="e2e-..."`. The ID is attached to the report.
import { After, Before, setDefaultTimeout, setWorldConstructor, World } from "@cucumber/cucumber";
import { randomUUID } from "node:crypto";
import { request } from "playwright-core";
import { AssistantApi, AuthApi, BorrowerApi, MortgageApi, ServicingApi } from "../api/apis.mjs";
import { Http } from "../api/http.mjs";

// Steps that wait for events poll for up to E2E_EVENT_TIMEOUT_MS (60 s); leave room on top.
setDefaultTimeout(120_000);

class JourneyWorld extends World {
  constructor(options) {
    super(options);
    this.correlationId = `e2e-${randomUUID()}`;
    this.username = null;      // who the current steps act as
    this.last = null;          // last response: { method, url, status, body, headers }
    this.borrowerId = null;
    this.mortgageId = null;
    this.balanceBefore = null;
    this.lastPayment = null;   // { body, idempotencyKey }
  }

  async open() {
    this.context = await request.newContext({ extraHTTPHeaders: { "X-Correlation-Id": this.correlationId } });
    const http = new Http(this.context);
    this.http = http;
    this.auth = new AuthApi(http);
    this.borrowers = new BorrowerApi(http);
    this.mortgages = new MortgageApi(http);
    this.servicing = new ServicingApi(http);
    this.assistant = new AssistantApi(http);
  }

  token(username = this.username) {
    if (!username) throw new Error("no user is logged in for this step");
    return this.auth.tokenFor(username);
  }

  /** Assertion message with the request and response, so a report line is enough to debug a failure. */
  describe(response = this.last) {
    if (!response) return "(no request was made)";
    return `${response.method} ${response.url} -> HTTP ${response.status} ${JSON.stringify(response.body)} ` +
      `(correlationId ${this.correlationId})`;
  }
}

setWorldConstructor(JourneyWorld);

Before(async function () {
  await this.open();
  this.attach(`correlationId: ${this.correlationId}`);
});

After(async function ({ result }) {
  if (result?.status === "FAILED" && this.last) this.attach(`last response: ${this.describe()}`);
  await this.context?.dispose();
});
