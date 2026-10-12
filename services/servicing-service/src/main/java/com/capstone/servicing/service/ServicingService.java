package com.capstone.servicing.service;

import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.repository.ServicingHistoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional; // 1. Import this

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Service
public class ServicingService {

    private final ServicingHistoryRepository servicingHistoryRepository;

    public ServicingService(ServicingHistoryRepository servicingHistoryRepository) {
        this.servicingHistoryRepository = servicingHistoryRepository;
    }

    public List<ServicingHistory> getServicingHistory(Long mortgageId) {
        return servicingHistoryRepository.findByMortgageId(mortgageId);
    }

    public Map<String, Object> getDelinquencyStatus(Long mortgageId) {
        // Basic business logic / stub returning evaluation metrics
        List<ServicingHistory> history = servicingHistoryRepository.findByMortgageId(mortgageId);
        boolean isDelinquent = history.stream().anyMatch(h -> "PAYMENT_MISSED".equals(h.getEventType()));

        return Map.of(
                "mortgageId", mortgageId,
                "isDelinquent", isDelinquent,
                "status", isDelinquent ? "DELINQUENT" : "CURRENT"
        );
    }

    @Transactional
    public ServicingHistory createServicingEvent(Long mortgageId, String eventType, String description) {
        ServicingHistory event = new ServicingHistory();
        event.setMortgageId(mortgageId);
        event.setEventType(eventType);
        event.setDescription(description);
        event.setCreatedAt(LocalDateTime.now());
        return servicingHistoryRepository.save(event);
    }
}
