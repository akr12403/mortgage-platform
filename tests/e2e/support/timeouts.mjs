import { eventTimeoutMs } from "./config.mjs";

/** Polling options for steps that wait for an event to reach a consumer. */
export function eventuallyTimeout() {
  return { timeoutMs: eventTimeoutMs, intervalMs: 2_000 };
}
