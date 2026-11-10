// Thin wrapper over Playwright's APIRequestContext: every call returns { status, body, headers } and never throws on
// an HTTP error status, so steps can assert on 4xx/5xx. Headers are lower-case (Playwright's convention).
export class Http {
  /** @param {import("playwright-core").APIRequestContext} context */
  constructor(context) {
    this.context = context;
  }

  async call(method, url, { token, body, headers } = {}) {
    const response = await this.context.fetch(url, {
      method,
      data: body,
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...headers },
      failOnStatusCode: false,
      timeout: 20_000,
    });
    const text = await response.text();
    let parsed = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = text;
    }
    return { method, url, status: response.status(), body: parsed, headers: response.headers() };
  }
}
