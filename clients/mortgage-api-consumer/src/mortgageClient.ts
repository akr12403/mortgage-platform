import { AuthSession, FetchFn, Logger } from "./auth.js";
import { ClientConfig } from "./config.js";
import { AuthenticatedTransport } from "./http.js";

/** Shapes from docs/api/mortgage-service-openapi.yaml and servicing-service-openapi.yaml. */
export interface LoanTerms {
  loanExternalId: string;
  interestRate: number;
  termMonths: number;
  underwritingDecision: string;
}

export interface Mortgage {
  mortgageExternalId: string;
  borrowerExternalId: string;
  status: "PENDING" | "ACTIVE" | "DELINQUENT" | "PAID_OFF" | "DEFAULTED" | "DECLINED" | string;
  originalAmount: number;
  outstandingBalance: number;
  originationDate: string;
  loan?: LoanTerms | null;
}

export interface ServicingEvent {
  eventTime: string;
  eventType: string;
  description: string;
}

export interface ServicingHistory {
  mortgageExternalId: string;
  events: ServicingEvent[];
}

export interface MortgageCreateRequest {
  mortgageExternalId: string;
  borrowerExternalId: string;
  originalAmount: number;
  outstandingBalance: number;
  originationDate: string;
  loan?: LoanTerms;
}

const MORTGAGE_ID = /^MTG-\d{4}$/;

/** Client-side hygiene only (fail fast, no path tricks); the server still validates everything. */
function mortgageId(id: string): string {
  if (!MORTGAGE_ID.test(id)) {
    throw new TypeError(`mortgageExternalId must match MTG-#### (got ${JSON.stringify(id)})`);
  }
  return encodeURIComponent(id);
}

/** All methods are async, so every failure (bad input, HTTP error, network) arrives as a rejected promise. */
export class MortgageClient {
  constructor(
    private readonly transport: AuthenticatedTransport,
    private readonly urls: { mortgageBaseUrl: string; servicingBaseUrl: string },
  ) {}

  /** GET mortgage-service /api/v1/mortgages/{id} (all five roles). */
  async getMortgage(mortgageExternalId: string): Promise<Mortgage> {
    return this.transport.request<Mortgage>("GET", `${this.urls.mortgageBaseUrl}/api/v1/mortgages/${mortgageId(mortgageExternalId)}`);
  }

  /** GET servicing-service /api/v1/mortgages/{id}/servicing-history (all five roles). */
  async getServicingHistory(mortgageExternalId: string): Promise<ServicingHistory> {
    return this.transport.request<ServicingHistory>(
      "GET",
      `${this.urls.servicingBaseUrl}/api/v1/mortgages/${mortgageId(mortgageExternalId)}/servicing-history`,
    );
  }

  /** POST mortgage-service /api/v1/mortgages (ADMIN, UNDERWRITER only; anyone else gets 403 ACCESS_DENIED). */
  async createMortgage(request: MortgageCreateRequest): Promise<Mortgage> {
    mortgageId(request.mortgageExternalId);
    return this.transport.request<Mortgage>("POST", `${this.urls.mortgageBaseUrl}/api/v1/mortgages`, { body: request });
  }
}

export interface ConsumerDeps {
  fetch?: FetchFn;
  logger?: Logger;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

/** Wires session + transport + client from a validated config. */
export function createMortgageApiConsumer(config: ClientConfig, deps: ConsumerDeps = {}) {
  const session = new AuthSession({
    baseUrl: config.mortgageBaseUrl,
    credentials: { username: config.username, password: config.password },
    timeoutMs: config.timeoutMs,
    ...(deps.fetch ? { fetch: deps.fetch } : {}),
    ...(deps.logger ? { logger: deps.logger } : {}),
    ...(deps.now ? { now: deps.now } : {}),
  });
  const transport = new AuthenticatedTransport({
    session,
    timeoutMs: config.timeoutMs,
    ...(deps.fetch ? { fetch: deps.fetch } : {}),
    ...(deps.logger ? { logger: deps.logger } : {}),
    ...(deps.sleep ? { sleep: deps.sleep } : {}),
  });
  const client = new MortgageClient(transport, config);
  return { session, transport, client };
}
