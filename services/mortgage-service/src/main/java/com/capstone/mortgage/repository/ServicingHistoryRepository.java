package com.capstone.mortgage.repository;

import com.capstone.mortgage.entity.ServicingHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.UUID;

@Repository
public interface ServicingHistoryRepository extends JpaRepository<ServicingHistory, UUID> {
}