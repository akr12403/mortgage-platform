package com.capstone.servicing.controller;

import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.service.ServicingService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/mortgages")
public class ServicingController {

    private final ServicingService servicingService;

    public ServicingController(ServicingService servicingService) {
        this.servicingService = servicingService;
    }

    @GetMapping("/{id}/servicing-history")
    public ResponseEntity<List<ServicingHistory>> getServicingHistory(@PathVariable("id") Long id) {
        return ResponseEntity.ok(servicingService.getServicingHistory(id));
    }

    @GetMapping("/{id}/delinquency")
    public ResponseEntity<Map<String, Object>> getDelinquency(@PathVariable("id") Long id) {
        return ResponseEntity.ok(servicingService.getDelinquencyStatus(id));
    }

    @PostMapping("/{id}/servicing-events")
    public ResponseEntity<ServicingHistory> createServicingEvent(
            @PathVariable("id") Long id,
            @RequestBody Map<String, String> payload) {
        String eventType = payload.getOrDefault("eventType", "GENERAL_EVENT");
        String description = payload.get("description");
        ServicingHistory saved = servicingService.createServicingEvent(id, eventType, description);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
