import { ConfigError } from "./errors.js";

export interface ClientConfig {
  mortgageBaseUrl: string;
  servicingBaseUrl: string;
  username: string;
  password: string;
  timeoutMs: number;
  /** true when a base URL uses plain HTTP (only ever allowed for localhost unless ALLOW_INSECURE_HTTP=true) */
  usesInsecureHttp: boolean;
}

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "host.docker.internal"]);

/**
 * Validates a base URL: http(s) only, no credentials embedded in the URL, and HTTPS for anything that is not
 * local. Returns the URL without a trailing slash.
 */
export function validateBaseUrl(name: string, raw: string, allowInsecureHttp: boolean): { url: string; insecure: boolean } {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new ConfigError(`${name} is not a valid URL`);
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new ConfigError(`${name} must use https (or http for localhost)`);
  }
  if (parsed.username || parsed.password) {
    throw new ConfigError(`${name} must not contain credentials`);
  }
  const insecure = parsed.protocol === "http:";
  if (insecure && !LOCAL_HOSTS.has(parsed.hostname) && !allowInsecureHttp) {
    throw new ConfigError(
      `${name} uses plain HTTP for a non-local host (${parsed.hostname}); use https or set ALLOW_INSECURE_HTTP=true for a trusted lab network`,
    );
  }
  return { url: parsed.origin + parsed.pathname.replace(/\/+$/, ""), insecure };
}

/** Reads configuration from environment variables only. Tokens are never read from or written to disk. */
export function loadConfig(env: Record<string, string | undefined> = process.env): ClientConfig {
  const allowInsecureHttp = (env.ALLOW_INSECURE_HTTP ?? "").toLowerCase() === "true";
  const mortgage = validateBaseUrl("MORTGAGE_API_BASE", env.MORTGAGE_API_BASE ?? "http://localhost:8080", allowInsecureHttp);
  const servicing = validateBaseUrl("SERVICING_API_BASE", env.SERVICING_API_BASE ?? "http://localhost:8081", allowInsecureHttp);

  const password = env.MORTGAGE_API_PASSWORD || env.AUTH_SEED_PASSWORD || "";
  if (!password) {
    throw new ConfigError("Set MORTGAGE_API_PASSWORD (local dev: the AUTH_SEED_PASSWORD from the repo-root .env)");
  }
  const timeoutMs = Number(env.MORTGAGE_API_TIMEOUT_MS ?? "10000");
  if (!Number.isInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 120_000) {
    throw new ConfigError("MORTGAGE_API_TIMEOUT_MS must be an integer between 100 and 120000");
  }

  return {
    mortgageBaseUrl: mortgage.url,
    servicingBaseUrl: servicing.url,
    username: env.MORTGAGE_API_USERNAME || "servicing@capstone.local",
    password,
    timeoutMs,
    usesInsecureHttp: mortgage.insecure || servicing.insecure,
  };
}
