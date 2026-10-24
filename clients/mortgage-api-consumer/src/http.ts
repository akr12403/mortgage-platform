import { randomUUID } from "node:crypto";
import { AuthSession, FetchFn, Logger, networkError } from "./auth.js";
import { ApiError } from "./errors.js";

export interface TransportOptions {
  session: AuthSession;
  fetch?: FetchFn;
  timeoutMs?: number;
  /** How many times to honour a 429 Retry-After before giving up. */
  maxRateLimitRetries?: number;
  /** Upper bound for a single Retry-After wait, so a misbehaving server cannot stall the client. */
  maxRetryAfterSeconds?: number;
  sleep?: (ms: number) => Promise<void>;
  logger?: Logger;
}

export interface RequestOptions {
  body?: unknown;
  correlationId?: string;
  idempotencyKey?: string;
}

/**
 * Authenticated HTTP transport shared by all service clients.
 *  - Adds `Authorization: Bearer <token>` and an `X-Correlation-Id` to every call.
 *  - On 401: drops the rejected token, logs in again ONCE and retries ONCE. A second 401 is surfaced; it never loops.
 *    Retrying is safe even for POST: a 401 is produced by the security filter before any handler runs.
 *  - On 403: surfaced immediately. A permission problem is not fixed by retrying or re-authenticating.
 *  - On 429: waits for Retry-After (capped) up to `maxRateLimitRetries` times.
 */
export class AuthenticatedTransport {
  readonly #session: AuthSession;
  readonly #fetch: FetchFn;
  readonly #timeoutMs: number;
  readonly #maxRateLimitRetries: number;
  readonly #maxRetryAfterMs: number;
  readonly #sleep: (ms: number) => Promise<void>;
  readonly #log: Logger;

  constructor(options: TransportOptions) {
    this.#session = options.session;
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#timeoutMs = options.timeoutMs ?? 10_000;
    this.#maxRateLimitRetries = options.maxRateLimitRetries ?? 2;
    this.#maxRetryAfterMs = (options.maxRetryAfterSeconds ?? 10) * 1000;
    this.#sleep = options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.#log = options.logger ?? (() => {});
  }

  async request<T>(method: string, url: string, options: RequestOptions = {}): Promise<T> {
    const correlationId = options.correlationId ?? randomUUID();
    let reauthenticated = false;
    let rateLimitRetries = 0;

    for (;;) {
      const token = await this.#session.getAccessToken();
      const headers: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "X-Correlation-Id": correlationId,
      };
      if (options.body !== undefined) headers["Content-Type"] = "application/json";
      if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

      let response: Response;
      try {
        response = await this.#fetch(url, {
          method,
          headers,
          body: options.body === undefined ? null : JSON.stringify(options.body),
          signal: AbortSignal.timeout(this.#timeoutMs),
        });
      } catch (err) {
        throw networkError(err);
      }

      if (response.status === 401 && !reauthenticated) {
        const error = await ApiError.fromResponse(response);
        this.#log("http.unauthorized", { method, url, code: error.code, action: "re-login and retry once", correlationId });
        this.#session.invalidate(token);
        reauthenticated = true;
        continue;
      }

      if (response.status === 429 && rateLimitRetries < this.#maxRateLimitRetries) {
        const waitMs = Math.min(retryAfterMs(response.headers.get("Retry-After")), this.#maxRetryAfterMs);
        await response.body?.cancel();
        this.#log("http.rateLimited", { method, url, waitMs, correlationId });
        rateLimitRetries += 1;
        await this.#sleep(waitMs);
        continue;
      }

      if (!response.ok) {
        throw await ApiError.fromResponse(response);
      }
      if (response.status === 204) {
        return undefined as T;
      }
      return (await response.json()) as T;
    }
  }
}

/** Retry-After is either delta-seconds or an HTTP-date. Defaults to 1 s when absent or unparseable. */
export function retryAfterMs(header: string | null, now: number = Date.now()): number {
  if (header) {
    const seconds = Number(header);
    if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;
    const date = Date.parse(header);
    if (!Number.isNaN(date)) return Math.max(0, date - now);
  }
  return 1000;
}
