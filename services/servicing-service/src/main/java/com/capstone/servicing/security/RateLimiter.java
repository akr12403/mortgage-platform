package com.capstone.servicing.security;

import java.time.Clock;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Thread-safe in-memory fixed-window rate limiter (M6 Task 6.3).
 *
 * One window per key (e.g. "login-ip:192.168.65.1"). Good enough for a single instance; with several replicas
 * (M9) the counters move to a shared store such as Redis or the API gateway/WAF, as documented in
 * docs/security/security-controls.md.
 */
public class RateLimiter {

    public record Decision(boolean allowed, long retryAfterSeconds) {}

    private static final class Window {
        final long startMillis;
        final AtomicLong count = new AtomicLong();

        Window(long startMillis) {
            this.startMillis = startMillis;
        }
    }

    private static final int CLEANUP_EVERY = 1_000;

    private final Clock clock;
    private final Map<String, Window> windows = new ConcurrentHashMap<>();
    private final AtomicLong calls = new AtomicLong();

    public RateLimiter(Clock clock) {
        this.clock = clock;
    }

    public Decision tryAcquire(String key, int limit, Duration window) {
        long now = clock.millis();
        long windowMillis = window.toMillis();
        Window current = windows.compute(key, (k, existing) ->
                existing == null || now - existing.startMillis >= windowMillis ? new Window(now) : existing);
        long used = current.count.incrementAndGet();

        if (calls.incrementAndGet() % CLEANUP_EVERY == 0) {
            windows.entrySet().removeIf(e -> now - e.getValue().startMillis >= windowMillis);
        }
        if (used <= limit) {
            return new Decision(true, 0);
        }
        long retryAfterMillis = Math.max(0, current.startMillis + windowMillis - now);
        return new Decision(false, Math.max(1, (retryAfterMillis + 999) / 1000));
    }
}
