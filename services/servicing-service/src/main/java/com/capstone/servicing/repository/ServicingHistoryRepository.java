package com.capstone.servicing.repository;

import com.capstone.servicing.entity.ServicingHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface ServicingHistoryRepository extends JpaRepository<ServicingHistory, UUID> {
    List<ServicingHistory> findByMortgageIdOrderByEventTimeAsc(UUID mortgageId);
}
