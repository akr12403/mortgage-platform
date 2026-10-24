package com.capstone.servicing.service;

import com.capstone.servicing.dto.DelinquencyResponse;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.exception.ResourceNotFoundException;
import com.capstone.servicing.repository.ServicingHistoryRepository;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * servicing-service owns servicing_history, delinquency (snapshot projected from LoanDelinquent)
 * and event_inbox. It only READS mortgage to resolve MTG-* business IDs to internal UUIDs.
 */
@Service
public class ServicingService {

    private final ServicingHistoryRepository servicingHistoryRepository;
    private final JdbcTemplate jdbcTemplate;

    public ServicingService(ServicingHistoryRepository servicingHistoryRepository, JdbcTemplate jdbcTemplate) {
        this.servicingHistoryRepository = servicingHistoryRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public List<ServicingHistory> getServicingHistory(String mortgageExternalId) {
        UUID mortgageId = findMortgageId(mortgageExternalId);
        return servicingHistoryRepository.findByMortgageIdOrderByEventTimeAsc(mortgageId);
    }

    @Transactional(readOnly = true)
    public DelinquencyResponse getDelinquencyStatus(String mortgageExternalId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
                SELECT m.status, d.delinquent_since, d.days_past_due, d.severity
                FROM mortgage m LEFT JOIN delinquency d ON d.mortgage_id = m.id
                WHERE m.mortgage_external_id = ?
                """, mortgageExternalId);
        if (rows.isEmpty()) {
            throw ResourceNotFoundException.mortgage(mortgageExternalId);
        }
        Map<String, Object> row = rows.get(0);
        Object since = row.get("delinquent_since");
        Object daysPastDue = row.get("days_past_due");
        return new DelinquencyResponse(
                mortgageExternalId,
                (String) row.get("status"),
                since == null ? null : since.toString(),
                daysPastDue == null ? null : ((Number) daysPastDue).intValue(),
                (String) row.get("severity"));
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
            throw ResourceNotFoundException.mortgage(mortgageExternalId);
        }
        return ids.get(0);
    }
}
