// API objects: the API-level equivalent of page objects (the platform has no UI). Each class owns one service's
// routes and request shapes, so a contract change is fixed here and not in every step. Routes and fields follow
// docs/api/*-openapi.yaml.
import { seedPassword, urls } from "../support/config.mjs";

// One login per user per Cucumber worker: login is rate limited (10 a minute per account) and a token lasts 1 h.
const tokens = new Map();

export class AuthApi {
  constructor(http) {
    this.http = http;
  }

  login(username, password = seedPassword()) {
    return this.http.call("POST", `${urls.mortgage}/api/v1/auth/login`, { body: { username, password } });
  }

  async tokenFor(username) {
    if (!tokens.has(username)) {
      const response = await this.login(username);
      if (response.status !== 200) {
        throw new Error(`login failed for ${username}: HTTP ${response.status} ${JSON.stringify(response.body)}`);
      }
      tokens.set(username, response.body.accessToken);
    }
    return tokens.get(username);
  }
}

export class BorrowerApi {
  constructor(http) {
    this.http = http;
  }

  create(token, borrower) {
    return this.http.call("POST", `${urls.mortgage}/api/v1/borrowers`, { token, body: borrower });
  }

  get(token, borrowerId) {
    return this.http.call("GET", `${urls.mortgage}/api/v1/borrowers/${borrowerId}`, { token });
  }
}

export class MortgageApi {
  constructor(http) {
    this.http = http;
  }

  create(token, mortgage) {
    return this.http.call("POST", `${urls.mortgage}/api/v1/mortgages`, { token, body: mortgage });
  }

  get(token, mortgageId) {
    return this.http.call("GET", `${urls.mortgage}/api/v1/mortgages/${mortgageId}`, { token });
  }

  decide(token, mortgageId, decision) {
    return this.http.call("POST", `${urls.mortgage}/api/v1/mortgages/${mortgageId}/underwriting-decision`,
      { token, body: { decision } });
  }

  postPayment(token, mortgageId, payment, idempotencyKey) {
    return this.http.call("POST", `${urls.mortgage}/api/v1/mortgages/${mortgageId}/payments`,
      { token, body: payment, headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {} });
  }

  listPayments(token, mortgageId) {
    return this.http.call("GET", `${urls.mortgage}/api/v1/mortgages/${mortgageId}/payments`, { token });
  }

  runDelinquencyEvaluation(token) {
    return this.http.call("POST", `${urls.mortgage}/api/v1/delinquency-evaluations`, { token });
  }
}

export class ServicingApi {
  constructor(http) {
    this.http = http;
  }

  history(token, mortgageId) {
    return this.http.call("GET", `${urls.servicing}/api/v1/mortgages/${mortgageId}/servicing-history`, { token });
  }

  delinquency(token, mortgageId) {
    return this.http.call("GET", `${urls.servicing}/api/v1/mortgages/${mortgageId}/delinquency`, { token });
  }
}

export class AssistantApi {
  constructor(http) {
    this.http = http;
  }

  ready() {
    return this.http.call("GET", `${urls.assistant}/health/ready`);
  }

  ask(token, question, extra = {}) {
    return this.http.call("POST", `${urls.assistant}/api/v1/assistant/ask`, { token, body: { question, ...extra } });
  }
}
