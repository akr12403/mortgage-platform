package com.capstone.mortgage.security;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;

class RateLimiterTest {

    /** Minimal controllable clock. */
    static final class MutableClock extends Clock {
        private Instant now = Instant.parse("2026-03-15T12:00:00Z");

        void advance(Duration d) {
            now = now.plus(d);
        }

        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return now; }
    }

    @Test
    void allowsUpToLimitThenBlocksUntilWindowResets() {
        MutableClock clock = new MutableClock();
        RateLimiter limiter = new RateLimiter(clock);
        Duration minute = Duration.ofMinutes(1);

        assertThat(limiter.tryAcquire("k", 2, minute).allowed()).isTrue();
        assertThat(limiter.tryAcquire("k", 2, minute).allowed()).isTrue();
        RateLimiter.Decision blocked = limiter.tryAcquire("k", 2, minute);
        assertThat(blocked.allowed()).isFalse();
        assertThat(blocked.retryAfterSeconds()).isBetween(1L, 60L);

        assertThat(limiter.tryAcquire("other", 2, minute).allowed()).as("keys are independent").isTrue();

        clock.advance(Duration.ofSeconds(61));
        assertThat(limiter.tryAcquire("k", 2, minute).allowed()).as("new window").isTrue();
    }
}
