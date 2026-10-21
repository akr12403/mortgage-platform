package com.capstone.servicing.controller;

import com.capstone.servicing.dto.DelinquencyResponse;
import com.capstone.servicing.dto.ServicingEventRequest;
import com.capstone.servicing.dto.ServicingHistoryResponse;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.service.ServicingService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/mortgages")
public class ServicingController {

    private final ServicingService servicingService;

    public ServicingController(ServicingService servicingService) {
        this.servicingService = servicingService;
    }

    @GetMapping("/{id}/servicing-history")
    public ResponseEntity<ServicingHistoryResponse> getServicingHistory(@PathVariable("id") String id) {
        return ResponseEntity.ok(ServicingHistoryResponse.from(id, servicingService.getServicingHistory(id)));
    }

    @GetMapping("/{id}/delinquency")
    public ResponseEntity<DelinquencyResponse> getDelinquency(@PathVariable("id") String id) {
        return ResponseEntity.ok(servicingService.getDelinquencyStatus(id));
    }

    /** Manual servicing note (e.g. ESCROW_ANALYSIS); lifecycle events arrive via SQS instead. */
    @PostMapping("/{id}/servicing-events")
    public ResponseEntity<ServicingHistoryResponse.Event> createServicingEvent(
            @PathVariable("id") String id,
            @Valid @RequestBody ServicingEventRequest request) {
        ServicingHistory saved = servicingService.createServicingEvent(id, request.eventType(), request.description());
        return ResponseEntity.status(HttpStatus.CREATED).body(
                new ServicingHistoryResponse.Event(saved.getEventTime(), saved.getEventType(), saved.getDescription()));
    }
}
