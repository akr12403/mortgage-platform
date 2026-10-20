package com.capstone.servicing.service;

import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.repository.ServicingHistoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional; // 1. Import this
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Instant;
import java.util.UUID;
import java.util.List;
import java.util.Map;

@Service
public class ServicingService {

    private final ServicingHistoryRepository servicingHistoryRepository;
    private final JdbcTemplate jdbcTemplate;

    public ServicingService(ServicingHistoryRepository servicingHistoryRepository, JdbcTemplate jdbcTemplate) {
        this.servicingHistoryRepository = servicingHistoryRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<ServicingHistory> getServicingHistory(String mortgageExternalId) {
        UUID mortgageId = findMortgageId(mortgageExternalId);
        return servicingHistoryRepository.findByMortgageIdOrderByEventTimeAsc(mortgageId);
    }

    public Map<String, Object> getDelinquencyStatus(String mortgageExternalId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
                SELECT m.status, d.delinquent_since, d.days_past_due, d.severity
                FROM mortgage m LEFT JOIN delinquency d ON d.mortgage_id = m.id
                WHERE m.mortgage_external_id = ?
                """, mortgageExternalId);
        if (rows.isEmpty()) {
            throw new jakarta.persistence.EntityNotFoundException("Mortgage " + mortgageExternalId + " was not found");
        }
        Map<String, Object> result = new java.util.LinkedHashMap<>();
        result.put("mortgageExternalId", mortgageExternalId);
        result.put("status", rows.get(0).get("status"));
        result.put("delinquentSince", rows.get(0).get("delinquent_since"));
        result.put("daysPastDue", rows.get(0).get("days_past_due"));
        result.put("severity", rows.get(0).get("severity"));
        return result;
    }

    @Transactional
    public ServicingHistory createServicingEvent(String mortgageExternalId, String eventType, String description) {
        ServicingHistory event = new ServicingHistory();
        event.setMortgageId(findMortgageId(mortgageExternalId));
        event.setEventType(eventType);
        event.setDescription(description);
        event.setEventTime(Instant.now());
        return servicingHistoryRepository.save(event);
    }

    public UUID findMortgageId(String mortgageExternalId) {
        List<UUID> ids = jdbcTemplate.query("SELECT id FROM mortgage WHERE mortgage_external_id = ?",
                (resultSet, rowNum) -> resultSet.getObject("id", UUID.class), mortgageExternalId);
        if (ids.isEmpty()) {
            throw new jakarta.persistence.EntityNotFoundException("Mortgage " + mortgageExternalId + " was not found");
        }
        return ids.get(0);
    }
}
