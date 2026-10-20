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
import org.springframework.transaction.support.TransactionTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public class EventConsumerService {

    private static final Logger logger = LoggerFactory.getLogger(EventConsumerService.class);

    private final SqsClient sqsClient;
    private final ServicingHistoryRepository historyRepository;
    private final EventInboxRepository inboxRepository;
    private final ObjectMapper objectMapper;
    private final ServicingService servicingService;
    private final TransactionTemplate transactionTemplate;

    @Value("${aws.sqs.queue-url:http://localstack:4566/000000000000/capstone-mortgage-servicing-dev}")
    private String queueUrl;

    public EventConsumerService(SqsClient sqsClient,
                                ServicingHistoryRepository historyRepository,
                                EventInboxRepository inboxRepository,
                                ObjectMapper objectMapper,
                                ServicingService servicingService,
                                TransactionTemplate transactionTemplate) {
        this.sqsClient = sqsClient;
        this.historyRepository = historyRepository;
        this.inboxRepository = inboxRepository;
        this.objectMapper = objectMapper;
        this.servicingService = servicingService;
        this.transactionTemplate = transactionTemplate;
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
            logger.error("Unable to poll servicing event queue {}", queueUrl, e);
        }
    }

    public void processMessage(Message message) {
        try {
            // Handle SNS JSON envelope wrapping if applicable
            JsonNode snsWrapper = objectMapper.readTree(message.body());
            String rawPayload = snsWrapper.has("Message") ? snsWrapper.get("Message").asText() : message.body();

            JsonNode eventEnvelope = objectMapper.readTree(rawPayload);
            UUID eventId = UUID.fromString(eventEnvelope.get("eventId").asText());
            String eventType = eventEnvelope.path("eventType").asText();
            String schemaVersion = eventEnvelope.path("schemaVersion").asText();
            String correlationId = eventEnvelope.path("correlationId").asText();
            if (schemaVersion.isBlank() || correlationId.isBlank()) {
                throw new IllegalArgumentException("Event envelope is missing schemaVersion or correlationId");
            }
            JsonNode payload = eventEnvelope.get("payload");

            if (!payload.hasNonNull("mortgageExternalId")) {
                throw new IllegalArgumentException("Event payload is missing mortgageExternalId");
            }
            String mortgageExternalId = payload.get("mortgageExternalId").asText();
            transactionTemplate.executeWithoutResult(status -> {
                if (inboxRepository.existsByEventId(eventId)) {
                    return;
                }

                ServicingHistory history = new ServicingHistory();
                history.setEventType(eventType);
                history.setEventTime(Instant.now());
                history.setMortgageId(servicingService.findMortgageId(mortgageExternalId));
                history.setDescription(describeEvent(eventType, payload));

                historyRepository.save(history);
                inboxRepository.save(new EventInbox(eventId));
            });

            // Acknowledge only after the database transaction commits.
            acknowledgeMessage(message);

        } catch (Exception e) {
            logger.error("Failed to process servicing event; message will remain for retry", e);
        }
    }

    private String describeEvent(String eventType, JsonNode payload) {
        return switch (eventType) {
            case "MortgageCreated" -> "Mortgage created with amount: " + payload.path("originalAmount").asText();
            case "PaymentReceived" -> "Payment received: " + payload.path("paymentAmount").asText();
            case "PaymentMissed" -> "Payment missed; " + payload.path("daysPastDue").asText() + " days past due";
            case "LoanApproved" -> "Loan approval decision: " + payload.path("underwritingDecision").asText();
            case "LoanDelinquent" -> "Loan delinquent; " + payload.path("daysPastDue").asText() + " days past due";
            default -> "Processed event: " + eventType;
        };
    }

    private void acknowledgeMessage(Message message) {
        DeleteMessageRequest deleteRequest = DeleteMessageRequest.builder()
                .queueUrl(queueUrl)
                .receiptHandle(message.receiptHandle())
                .build();
        sqsClient.deleteMessage(deleteRequest);
    }
}