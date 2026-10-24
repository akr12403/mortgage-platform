import { ApiError } from "./errors.js";

export type FetchFn = typeof fetch;
export type Logger = (event: string, details?: Record<string, unknown>) => void;

export interface Credentials {
  username: string;
  password: string;
}

/** POST /api/v1/auth/login response (mortgage-service, M6 Task 6.1). */
export interface LoginResponse {
  accessToken: string;
  tokenType: string;
  expiresInSeconds: number;
  roles: string[];
}

export interface AuthSessionOptions {
  /** mortgage-service base URL; the only service that issues tokens */
  baseUrl: string;
  credentials: Credentials;
  fetch?: FetchFn;
  timeoutMs?: number;
  /** Re-login this many seconds before the token's expiry so requests never race the deadline. */
  refreshSkewSeconds?: number;
  now?: () => number;
  logger?: Logger;
}

/**
 * Holds the access token IN MEMORY ONLY (never on disk, never in logs) and renews it by logging in again.
 *
 * The platform issues short-lived access tokens without refresh tokens (docs/security/authentication.md), so
 * "refresh" here means re-login with the configured credentials:
 *  - proactively, when the token is within `refreshSkewSeconds` of its expiry;
 *  - reactively, when a service answers 401 (expired, revoked by a JWT_SECRET rotation, or otherwise rejected).
 * Concurrent callers share a single in-flight login, so a burst of 401s causes exactly one login request.
 */
export class AuthSession {
  readonly #baseUrl: string;
  readonly #credentials: Credentials;
  readonly #fetch: FetchFn;
  readonly #timeoutMs: number;
  readonly #skewMs: number;
  readonly #now: () => number;
  readonly #log: Logger;

  #token: string | null = null;
  #expiresAt = 0;
  #roles: readonly string[] = [];
  #inflight: Promise<string> | null = null;
  #rejected = false;

  constructor(options: AuthSessionOptions) {
    this.#baseUrl = options.baseUrl;
    this.#credentials = { ...options.credentials };
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#timeoutMs = options.timeoutMs ?? 10_000;
    this.#skewMs = (options.refreshSkewSeconds ?? 30) * 1000;
    this.#now = options.now ?? Date.now;
    this.#log = options.logger ?? (() => {});
  }

  get roles(): readonly string[] {
    return this.#roles;
  }

  get isAuthenticated(): boolean {
    return this.#token !== null && this.#now() < this.#expiresAt;
  }

  /** Milliseconds until the current token expires (0 when there is none). */
  get expiresInMs(): number {
    return this.#token === null ? 0 : Math.max(0, this.#expiresAt - this.#now());
  }

  /** Logs in now (or joins a login already in progress). */
  login(): Promise<string> {
    if (!this.#inflight) {
      this.#inflight = this.#doLogin().finally(() => {
        this.#inflight = null;
      });
    }
    return this.#inflight;
  }

  /** Returns a usable token, logging in first if there is none or it is about to expire. */
  async getAccessToken(): Promise<string> {
    if (this.#token !== null && this.#now() < this.#expiresAt - this.#skewMs) {
      return this.#token;
    }
    const reason = this.#token !== null ? "token expiring soon" : this.#rejected ? "token rejected by server (401)" : "no token yet";
    this.#log("auth.login", { reason });
    return this.login();
  }

  /**
   * Called when a service rejected `token` with 401. Only clears the session if that token is still the current
   * one, so a request that failed with an old token never throws away a fresh token another request just got.
   */
  invalidate(token: string): void {
    if (this.#token === token) {
      this.#token = null;
      this.#expiresAt = 0;
      this.#rejected = true;
    }
  }

  /** Forget the token (e.g. on logout). */
  clear(): void {
    this.#token = null;
    this.#expiresAt = 0;
    this.#roles = [];
  }

  /**
   * Demo aid (`npm run demo`): tamper with the in-memory token's signature so the next call gets a REAL 401
   * INVALID_TOKEN from the server, exactly as an expired token would. Lets the demo show the re-login path
   * without waiting an hour for JWT_TTL_SECONDS to elapse.
   */
  forceTokenRejectionForDemo(): void {
    if (this.#token !== null) {
      const last = this.#token.slice(-1);
      this.#token = this.#token.slice(0, -1) + (last === "A" ? "B" : "A");
    }
  }

  /** Never expose the token through console.log / util.inspect / JSON.stringify. */
  toJSON(): Record<string, unknown> {
    return { authenticated: this.isAuthenticated, roles: this.#roles, expiresInMs: this.expiresInMs };
  }

  [Symbol.for("nodejs.util.inspect.custom")](): string {
    return `AuthSession ${JSON.stringify(this.toJSON())}`;
  }

  async #doLogin(): Promise<string> {
    let response: Response;
    try {
      response = await this.#fetch(`${this.#baseUrl}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(this.#credentials),
        signal: AbortSignal.timeout(this.#timeoutMs),
      });
    } catch (err) {
      throw networkError(err);
    }
    if (!response.ok) {
      // No automatic retry on a failed login: retrying bad credentials is exactly what the server's
      // login rate limit (429 RATE_LIMITED) is there to stop.
      throw await ApiError.fromResponse(response);
    }
    const body = (await response.json()) as Partial<LoginResponse>;
    if (typeof body.accessToken !== "string" || typeof body.expiresInSeconds !== "number") {
      throw new ApiError(response.status, "INVALID_LOGIN_RESPONSE", "Login response did not contain a token");
    }
    this.#token = body.accessToken;
    this.#rejected = false;
    this.#expiresAt = this.#now() + body.expiresInSeconds * 1000;
    this.#roles = Object.freeze([...(body.roles ?? [])]);
    this.#log("auth.loggedIn", { roles: this.#roles, expiresInSeconds: body.expiresInSeconds });
    return body.accessToken;
  }
}

export function networkError(err: unknown): ApiError {
  const timeout = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
  return timeout
    ? new ApiError(0, "TIMEOUT", "The request timed out")
    : new ApiError(0, "NETWORK_ERROR", "Could not reach the service");
}
