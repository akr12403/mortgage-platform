package com.capstone.servicing.dto;

import com.capstone.servicing.entity.ServicingHistory;

import java.time.Instant;
import java.util.List;

public record ServicingHistoryResponse(String mortgageExternalId, List<Event> events) {
    public static ServicingHistoryResponse from(String mortgageExternalId, List<ServicingHistory> history) {
        return new ServicingHistoryResponse(mortgageExternalId, history.stream()
                .map(event -> new Event(event.getEventTime(), event.getEventType(), event.getDescription()))
                .toList());
    }

    public record Event(Instant eventTime, String eventType, String description) {}
}