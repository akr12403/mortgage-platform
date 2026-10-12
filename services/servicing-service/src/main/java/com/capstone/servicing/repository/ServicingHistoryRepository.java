package com.capstone.servicing.repository;

import com.capstone.servicing.entity.ServicingHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ServicingHistoryRepository extends JpaRepository<ServicingHistory, Long> {
    List<ServicingHistory> findByMortgageId(Long mortgageId);
}
