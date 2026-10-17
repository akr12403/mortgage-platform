package com.capstone.servicing.repository;

import com.capstone.servicing.entity.EventInbox;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface EventInboxRepository extends JpaRepository<EventInbox, UUID> {
    boolean existsByEventId(UUID eventId);
}