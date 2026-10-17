package com.capstone.servicing.service;

import com.capstone.servicing.entity.EventInbox;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.repository.EventInboxRepository;
import com.capstone.servicing.repository.ServicingHistoryRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

@Service
public class EventConsumerService {

    private final SqsClient sqsClient;
    private final ServicingHistoryRepository historyRepository;
    private final EventInboxRepository inboxRepository;
    private final ObjectMapper objectMapper;

    @Value("${aws.sqs.queue-url:http://localhost:4566/000000000000/capstone-mortgage-servicing-dev}")
    private String queueUrl;

    public EventConsumerService(SqsClient sqsClient,
                                ServicingHistoryRepository historyRepository,
                                EventInboxRepository inboxRepository,
                                ObjectMapper objectMapper) {
        this.sqsClient = sqsClient;
        this.historyRepository = historyRepository;
        this.inboxRepository = inboxRepository;
        this.objectMapper = objectMapper;
    }

    @Scheduled(fixedRate = 5000)
    public void pollEvents() {
        try {
            ReceiveMessageRequest receiveRequest = ReceiveMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .maxNumberOfMessages(5)
                    .waitTimeSeconds(2)
                    .build();

            List<Message> messages = sqsClient.receiveMessage(receiveRequest).messages();

            for (Message message : messages) {
                processMessage(message);
            }
        } catch (Exception e) {
            // Suppress connection exceptions if LocalStack isn't running yet during startup
        }
    }

    @Transactional
    public void processMessage(Message message) {
        try {
            // Handle SNS JSON envelope wrapping if applicable
            JsonNode snsWrapper = objectMapper.readTree(message.body());
            String rawPayload = snsWrapper.has("Message") ? snsWrapper.get("Message").asText() : message.body();

            JsonNode eventEnvelope = objectMapper.readTree(rawPayload);
            UUID eventId = UUID.fromString(eventEnvelope.get("eventId").asText());
            String eventType = eventEnvelope.get("eventType").asText();
            JsonNode payload = eventEnvelope.get("payload");

            // 1. Idempotency Check using event_inbox
            if (inboxRepository.existsByEventId(eventId)) {
                acknowledgeMessage(message);
                return;
            }

            // 2. Map payload details to ServicingHistory
            ServicingHistory history = new ServicingHistory();
            history.setEventId(eventId.toString());
            history.setEventType(eventType);
            history.setCreatedAt(LocalDateTime.now());

            // Extract mortgage reference safely
            if (payload.has("mortgageExternalId")) {
                String mtgExtId = payload.get("mortgageExternalId").asText();
                // Parse numeric ID if your DB column expects Long (e.g. "MTG-1" -> 1L)
                try {
                    Long numericId = Long.parseLong(mtgExtId.replaceAll("[^0-9]", ""));
                    history.setMortgageId(numericId);
                } catch (Exception e) {
                    history.setMortgageId(0L); // fallback
                }
            } else {
                history.setMortgageId(0L);
            }

            switch (eventType) {
                case "MortgageCreated" -> history.setDescription("Mortgage created with amount: " + payload.path("originalAmount").asText());
                case "PaymentReceived" -> history.setDescription("Payment received: " + payload.path("paymentAmount").asText());
                default -> history.setDescription("Processed event: " + eventType);
            }

            // Save history and record event in inbox
            historyRepository.save(history);
            inboxRepository.save(new EventInbox(eventId));

            // 3. Acknowledge and delete message from queue
            acknowledgeMessage(message);

        } catch (Exception e) {
            // Leave message in queue for retry / DLQ routing if processing fails
        }
    }

    private void acknowledgeMessage(Message message) {
        DeleteMessageRequest deleteRequest = DeleteMessageRequest.builder()
                .queueUrl(queueUrl)
                .receiptHandle(message.receiptHandle())
                .build();
        sqsClient.deleteMessage(deleteRequest);
    }
}