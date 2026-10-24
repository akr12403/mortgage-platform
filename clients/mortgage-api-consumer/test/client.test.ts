import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { inspect } from "node:util";

import { AuthSession } from "../src/auth.js";
import { loadConfig, validateBaseUrl } from "../src/config.js";
import { ApiError, ConfigError } from "../src/errors.js";
import { retryAfterMs } from "../src/http.js";
import { createMortgageApiConsumer } from "../src/mortgageClient.js";

const BASE = "http://localhost:8080";
const SERVICING = "http://localhost:8081";
const MORTGAGE = { mortgageExternalId: "MTG-1001", borrowerExternalId: "BOR-001", status: "ACTIVE", originalAmount: 310000, outstandingBalance: 305000, originationDate: "2024-01-15" };

interface Call {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
}

type Reply = { status: number; body?: unknown; headers?: Record<string, string> };

/** A scripted fake server: records every call and answers via `route`. Tokens are "t1", "t2", ... per login. */
function fakeServer(route: (call: Call, state: { logins: number }) => Reply | undefined, tokenTtlSeconds = 3600) {
  const calls: Call[] = [];
  const state = { logins: 0 };
  const fetchFn = (async (input: string | URL | Request, init?: RequestInit) => {
    const headers = Object.fromEntries(new Headers(init?.headers).entries());
    const call: Call = { method: init?.method ?? "GET", url: String(input), headers, body: (init?.body as string | null) ?? null };
    calls.push(call);
    let reply: Reply | undefined;
    if (call.url === `${BASE}/api/v1/auth/login`) {
      state.logins += 1;
      reply = route(call, state) ?? {
        status: 200,
        body: { accessToken: `t${state.logins}`, tokenType: "Bearer", expiresInSeconds: tokenTtlSeconds, roles: ["SERVICING_AGENT"] },
      };
    } else {
      reply = route(call, state) ?? { status: 404, body: { code: "NOT_FOUND", message: "no route", correlationId: "c-404" } };
    }
    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status: reply.status,
      headers: { "Content-Type": "application/json", ...(reply.headers ?? {}) },
    });
  }) as typeof fetch;
  return { fetch: fetchFn, calls, state };
}

function consumer(server: ReturnType<typeof fakeServer>, extra: { now?: () => number; sleeps?: number[] } = {}) {
  const config = loadConfig({ MORTGAGE_API_PASSWORD: "seed-password-123" });
  const sleeps = extra.sleeps ?? [];
  return createMortgageApiConsumer(config, {
    fetch: server.fetch,
    sleep: async (ms) => {
      sleeps.push(ms);
    },
    ...(extra.now ? { now: extra.now } : {}),
  });
}

const bearer = (call: Call | undefined) => call?.headers["authorization"];

describe("login and authenticated calls", () => {
  it("logs in once, keeps the token in memory and sends it as a Bearer header to both services", async () => {
    const server = fakeServer((call) => {
      if (call.url === `${BASE}/api/v1/mortgages/MTG-1001`) return { status: 200, body: MORTGAGE };
      if (call.url === `${SERVICING}/api/v1/mortgages/MTG-1001/servicing-history`)
        return { status: 200, body: { mortgageExternalId: "MTG-1001", events: [{ eventTime: "t", eventType: "PAYMENT_POSTED", description: "d" }] } };
      return undefined;
    });
    const { client, session } = consumer(server);

    const mortgage = await client.getMortgage("MTG-1001");
    const history = await client.getServicingHistory("MTG-1001");

    assert.equal(mortgage.status, "ACTIVE");
    assert.equal(history.events.length, 1);
    assert.equal(server.state.logins, 1, "one login for both calls");
    const login = server.calls[0];
    assert.deepEqual(JSON.parse(login?.body ?? "{}"), { username: "servicing@capstone.local", password: "seed-password-123" });
    assert.equal(bearer(server.calls[1]), "Bearer t1");
    assert.equal(bearer(server.calls[2]), "Bearer t1");
    assert.ok(server.calls[1]?.headers["x-correlation-id"], "correlation id sent");
    assert.deepEqual(session.roles, ["SERVICING_AGENT"]);
  });

  it("rejects malformed mortgage IDs before any request is sent", async () => {
    const server = fakeServer(() => undefined);
    const { client } = consumer(server);
    await assert.rejects(client.getMortgage("MTG-1001/../../admin"), TypeError);
    await assert.rejects(client.getMortgage("1001"), TypeError);
    assert.equal(server.calls.length, 0);
  });
});

describe("expired or rejected token", () => {
  it("on 401 re-logs in once and retries the request with the new token", async () => {
    const server = fakeServer((call) => {
      if (call.url.endsWith("/MTG-1001")) {
        return bearer(call) === "Bearer t1"
          ? { status: 401, body: { code: "INVALID_TOKEN", message: "Access token is invalid or expired", correlationId: "c1" } }
          : { status: 200, body: MORTGAGE };
      }
      return undefined;
    });
    const { client } = consumer(server);

    const mortgage = await client.getMortgage("MTG-1001");

    assert.equal(mortgage.mortgageExternalId, "MTG-1001");
    assert.equal(server.state.logins, 2);
    assert.deepEqual(server.calls.map((c) => bearer(c) ?? "login"), ["login", "Bearer t1", "login", "Bearer t2"]);
  });

  it("a second 401 after re-login is surfaced, never an infinite loop", async () => {
    const server = fakeServer((call) =>
      call.url.endsWith("/MTG-1001") ? { status: 401, body: { code: "INVALID_TOKEN", message: "nope", correlationId: "c2" } } : undefined,
    );
    const { client } = consumer(server);

    await assert.rejects(client.getMortgage("MTG-1001"), (err: unknown) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 401);
      assert.equal(err.code, "INVALID_TOKEN");
      assert.equal(err.correlationId, "c2");
      return true;
    });
    assert.equal(server.state.logins, 2);
    assert.equal(server.calls.length, 4);
  });

  it("re-logs in proactively when the token is about to expire (no 401 round trip)", async () => {
    let now = 1_000_000;
    const server = fakeServer((call) => (call.url.endsWith("/MTG-1001") ? { status: 200, body: MORTGAGE } : undefined), 60);
    const { client } = consumer(server, { now: () => now });

    await client.getMortgage("MTG-1001");
    now += 20_000; // 40 s left: still fresh
    await client.getMortgage("MTG-1001");
    assert.equal(server.state.logins, 1);
    now += 15_000; // 25 s left: inside the 30 s skew
    await client.getMortgage("MTG-1001");

    assert.equal(server.state.logins, 2);
    assert.equal(bearer(server.calls.at(-1)), "Bearer t2");
  });

  it("concurrent 401s share a single re-login", async () => {
    const server = fakeServer((call) => {
      if (call.url.endsWith("/MTG-1001")) {
        return bearer(call) === "Bearer t1" ? { status: 401, body: { code: "INVALID_TOKEN", message: "expired" } } : { status: 200, body: MORTGAGE };
      }
      return undefined;
    });
    const { client, session } = consumer(server);
    await session.login();

    const results = await Promise.all([client.getMortgage("MTG-1001"), client.getMortgage("MTG-1001"), client.getMortgage("MTG-1001")]);

    assert.equal(results.length, 3);
    assert.equal(server.state.logins, 2, "initial login + exactly one re-login");
  });

  it("a failed login is surfaced and not retried (the server rate-limits logins)", async () => {
    const server = fakeServer((call) =>
      call.url.endsWith("/auth/login") ? { status: 401, body: { code: "INVALID_CREDENTIALS", message: "Invalid username or password" } } : undefined,
    );
    const { client } = consumer(server);

    await assert.rejects(client.getMortgage("MTG-1001"), (err: unknown) => err instanceof ApiError && err.code === "INVALID_CREDENTIALS");
    assert.equal(server.state.logins, 1);
    assert.equal(server.calls.length, 1, "no protected call attempted without a token");
  });
});

describe("authorization and throttling", () => {
  it("403 is surfaced immediately: no re-login, no retry", async () => {
    const server = fakeServer((call) =>
      call.url === `${BASE}/api/v1/mortgages` && call.method === "POST"
        ? { status: 403, body: { code: "ACCESS_DENIED", message: "You do not have permission to perform this action", correlationId: "c403" } }
        : undefined,
    );
    const { client } = consumer(server);

    await assert.rejects(
      client.createMortgage({ mortgageExternalId: "MTG-9998", borrowerExternalId: "BOR-001", originalAmount: 1, outstandingBalance: 1, originationDate: "2025-06-01" }),
      (err: unknown) => err instanceof ApiError && err.status === 403 && err.code === "ACCESS_DENIED" && err.correlationId === "c403",
    );
    assert.equal(server.state.logins, 1);
    assert.equal(server.calls.length, 2);
    assert.equal(server.calls[1]?.headers["content-type"], "application/json");
  });

  it("429 waits for Retry-After (capped) and retries a bounded number of times", async () => {
    let attempts = 0;
    const server = fakeServer((call) => {
      if (!call.url.endsWith("/MTG-1001")) return undefined;
      attempts += 1;
      return attempts <= 2
        ? { status: 429, body: { code: "RATE_LIMITED", message: "Too many requests" }, headers: { "Retry-After": attempts === 1 ? "3" : "600" } }
        : { status: 200, body: MORTGAGE };
    });
    const sleeps: number[] = [];
    const { client } = consumer(server, { sleeps });

    await client.getMortgage("MTG-1001");
    assert.deepEqual(sleeps, [3000, 10_000], "honours Retry-After, capped at 10 s");

    attempts = -10; // now keep answering 429
    await assert.rejects(client.getMortgage("MTG-1001"), (err: unknown) => err instanceof ApiError && err.status === 429 && err.code === "RATE_LIMITED");
  });

  it("parses Retry-After seconds and HTTP-dates", () => {
    assert.equal(retryAfterMs("5"), 5000);
    assert.equal(retryAfterMs(null), 1000);
    assert.equal(retryAfterMs("garbage"), 1000);
    assert.equal(retryAfterMs(new Date(10_000).toUTCString(), 4000), 6000);
  });
});

describe("token and secret hygiene", () => {
  it("never exposes the token through JSON.stringify, util.inspect or errors", async () => {
    const server = fakeServer((call) =>
      call.url.endsWith("/MTG-1001") ? { status: 500, body: { code: "INTERNAL_ERROR", message: "An unexpected error occurred" } } : undefined,
    );
    const { client, session } = consumer(server);
    await session.login();

    assert.ok(!JSON.stringify(session).includes("t1"));
    assert.ok(!inspect(session, { showHidden: true, depth: 5 }).includes("t1"));
    assert.ok(!inspect(session).includes("seed-password-123"));
    const err = await client.getMortgage("MTG-1001").catch((e: unknown) => e);
    assert.ok(err instanceof ApiError);
    assert.ok(!inspect(err, { showHidden: true }).includes("Bearer"));
    assert.ok(!JSON.stringify(err).includes("t1"));
  });

  it("network failures and timeouts become ApiErrors without request details", async () => {
    const failing = (async () => {
      throw Object.assign(new Error("connect ECONNREFUSED 127.0.0.1:8080"), { name: "TypeError" });
    }) as typeof fetch;
    const session = new AuthSession({ baseUrl: BASE, credentials: { username: "u", password: "p" }, fetch: failing });
    await assert.rejects(session.login(), (err: unknown) => err instanceof ApiError && err.code === "NETWORK_ERROR" && err.status === 0);

    const slow = (async () => {
      throw Object.assign(new Error("The operation was aborted due to timeout"), { name: "TimeoutError" });
    }) as typeof fetch;
    const timedOut = new AuthSession({ baseUrl: BASE, credentials: { username: "u", password: "p" }, fetch: slow });
    await assert.rejects(timedOut.login(), (err: unknown) => err instanceof ApiError && err.code === "TIMEOUT");
  });
});

describe("configuration", () => {
  it("reads everything from env, with local defaults", () => {
    const config = loadConfig({ AUTH_SEED_PASSWORD: "from-seed" });
    assert.equal(config.mortgageBaseUrl, BASE);
    assert.equal(config.servicingBaseUrl, SERVICING);
    assert.equal(config.password, "from-seed");
    assert.equal(config.usesInsecureHttp, true);
  });

  it("requires a password", () => {
    assert.throws(() => loadConfig({}), ConfigError);
  });

  it("requires HTTPS for non-local hosts unless explicitly allowed", () => {
    assert.throws(() => validateBaseUrl("X", "http://api.example.com", false), ConfigError);
    assert.equal(validateBaseUrl("X", "http://api.example.com", true).insecure, true);
    assert.deepEqual(validateBaseUrl("X", "https://api.example.com/", false), { url: "https://api.example.com", insecure: false });
    assert.equal(validateBaseUrl("X", "http://host.docker.internal:8080", false).url, "http://host.docker.internal:8080");
  });

  it("rejects credentials in URLs and non-http schemes", () => {
    assert.throws(() => validateBaseUrl("X", "https://user:pw@api.example.com", false), ConfigError);
    assert.throws(() => validateBaseUrl("X", "file:///etc/passwd", false), ConfigError);
    assert.throws(() => validateBaseUrl("X", "not a url", false), ConfigError);
  });
});
