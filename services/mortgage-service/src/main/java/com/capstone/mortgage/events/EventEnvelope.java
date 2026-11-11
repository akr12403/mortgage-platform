package com.capstone.mortgage.events;

import java.time.Instant;
import java.util.UUID;

public record EventEnvelope<T>(
        String eventId,
        String eventType,
        String schemaVersion,
        Instant occurredAt,
        String correlationId,
        T payload
) {
    public static <T> EventEnvelope<T> wrap(String eventType, String correlationId, T payload) {
        return new EventEnvelope<>(
                UUID.randomUUID().toString(),
                eventType,
                "1.0",
                Instant.now(),
                correlationId != null ? correlationId : UUID.randomUUID().toString(),
                payload
        );
    }
}