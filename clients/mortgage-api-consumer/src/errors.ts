/** Error envelope returned by every platform service: { code, message, correlationId, timestamp }. */
export interface ErrorEnvelope {
  code?: string;
  message?: string;
  correlationId?: string;
  timestamp?: string;
}

/**
 * A failed API call. Carries the HTTP status and the server's error code/correlation id so callers can branch on
 * `code` (e.g. ACCESS_DENIED, RATE_LIMITED). It never contains the access token or the request headers.
 */
export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly correlationId?: string,
  ) {
    super(message);
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    let envelope: ErrorEnvelope = {};
    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      // non-JSON error body (e.g. a proxy page): fall back to the status line
    }
    return new ApiError(
      response.status,
      envelope.code ?? `HTTP_${response.status}`,
      envelope.message ?? (response.statusText || "Request failed"),
      envelope.correlationId ?? response.headers.get("X-Correlation-Id") ?? undefined,
    );
  }
}

/** Raised for missing/unsafe client configuration (bad base URL, missing credentials). */
export class ConfigError extends Error {
  override readonly name = "ConfigError";
}
