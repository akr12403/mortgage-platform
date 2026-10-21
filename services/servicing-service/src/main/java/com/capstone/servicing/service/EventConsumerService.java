package com.capstone.servicing.service;

import com.capstone.servicing.entity.EventInbox;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.repository.EventInboxRepository;
import com.capstone.servicing.repository.ServicingHistoryRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.QueueAttributeName;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;

import java.sql.Date;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * SQS consumer for the servicing queue (SNS topic capstone-mortgage-lifecycle-dev -> SQS).
 *
 * - Validates the event envelope (eventId, eventType, schemaVersion 1.x, correlationId, payload).
 * - Idempotent: event_inbox(event_id) dedupes; history + inbox are written in one transaction.
 * - Acknowledges (deletes) only after commit. On failure the message is left on the queue, SQS
 *   redelivers after the visibility timeout, and after maxReceiveCount receives SQS moves it to the DLQ.
 * - Unknown event types are acknowledged and skipped (forward compatible with new producers).
 */
@Service
public class EventConsumerService {

    private static final Logger logger = LoggerFactory.getLogger(EventConsumerService.class);
    private static final String SUPPORTED_SCHEMA_MAJOR = "1.";

    /** Lifecycle event -> servicing_history.event_type (servicing vocabulary, see event-catalog.md). */
    static final Map<String, String> HISTORY_EVENT_TYPES = Map.of(
            "MortgageCreated", "MORTGAGE_CREATED",
            "LoanApproved", "LOAN_APPROVED",
            "PaymentReceived", "PAYMENT_POSTED",
            "PaymentMissed", "PAYMENT_MISSED",
            "LoanDelinquent", "DELINQUENCY_ASSIGNED"
    );

    public enum Outcome { PROCESSED, DUPLICATE, SKIPPED, FAILED }

    private final SqsClient sqsClient;
    private final ServicingHistoryRepository historyRepository;
    private final EventInboxRepository inboxRepository;
    private final ObjectMapper objectMapper;
    private final ServicingService servicingService;
    private final TransactionTemplate transactionTemplate;
    private final JdbcTemplate jdbcTemplate;
    private final String queueUrl;
    private final int maxReceiveCount;
    private final boolean consumerEnabled;

    public EventConsumerService(SqsClient sqsClient,
                                ServicingHistoryRepository historyRepository,
                                EventInboxRepository inboxRepository,
                                ObjectMapper objectMapper,
                                ServicingService servicingService,
                                TransactionTemplate transactionTemplate,
                                JdbcTemplate jdbcTemplate,
                                @Value("${aws.sqs.queue-url}") String queueUrl,
                                @Value("${app.messaging.max-receive-count:3}") int maxReceiveCount,
                                @Value("${app.messaging.consumer-enabled:true}") boolean consumerEnabled) {
        this.sqsClient = sqsClient;
        this.historyRepository = historyRepository;
        this.inboxRepository = inboxRepository;
        this.objectMapper = objectMapper;
        this.servicingService = servicingService;
        this.transactionTemplate = transactionTemplate;
        this.jdbcTemplate = jdbcTemplate;
        this.queueUrl = queueUrl;
        this.maxReceiveCount = maxReceiveCount;
        this.consumerEnabled = consumerEnabled;
    }

    @Scheduled(fixedDelayString = "${app.messaging.poll-delay-ms:2000}")
    public void pollEvents() {
        if (!consumerEnabled) {
            return;
        }
        List<Message> messages;
        try {
            ReceiveMessageRequest receiveRequest = ReceiveMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .maxNumberOfMessages(5)
                    .waitTimeSeconds(5)
                    .attributeNames(QueueAttributeName.ALL)
                    .build();
            messages = sqsClient.receiveMessage(receiveRequest).messages();
        } catch (Exception e) {
            logger.error("Unable to poll servicing event queue {}", queueUrl, e);
            return;
        }
        for (Message message : messages) {
            processMessage(message);
        }
    }

    public Outcome processMessage(Message message) {
        int receiveCount = receiveCount(message);
        try {
            JsonNode envelope = parseEnvelope(message.body());
            UUID eventId = UUID.fromString(requiredText(envelope, "eventId"));
            String eventType = requiredText(envelope, "eventType");
            String schemaVersion = requiredText(envelope, "schemaVersion");
            String correlationId = requiredText(envelope, "correlationId");
            MDC.put("correlationId", correlationId);
            MDC.put("eventId", eventId.toString());

            if (!schemaVersion.startsWith(SUPPORTED_SCHEMA_MAJOR)) {
                throw new IllegalArgumentException("Unsupported schemaVersion " + schemaVersion + " for " + eventType);
            }
            String historyEventType = HISTORY_EVENT_TYPES.get(eventType);
            if (historyEventType == null) {
                logger.warn("Skipping unknown eventType {} (eventId={})", eventType, eventId);
                acknowledge(message);
                return Outcome.SKIPPED;
            }
            JsonNode payload = envelope.get("payload");
            if (payload == null || !payload.isObject()) {
                throw new IllegalArgumentException("Event envelope is missing payload");
            }
            String mortgageExternalId = requiredText(payload, "mortgageExternalId");

            Boolean processed = transactionTemplate.execute(status -> {
                if (inboxRepository.existsByEventId(eventId)) {
                    return false;
                }
                UUID mortgageId = servicingService.findMortgageId(mortgageExternalId);

                ServicingHistory history = new ServicingHistory();
                history.setMortgageId(mortgageId);
                history.setEventType(historyEventType);
                history.setEventTime(Instant.now());
                history.setDescription(describeEvent(eventType, payload));
                historyRepository.save(history);

                if ("LoanDelinquent".equals(eventType)) {
                    upsertDelinquencySnapshot(mortgageId, payload);
                }
                inboxRepository.save(new EventInbox(eventId));
                return true;
            });

            // Acknowledge only after the database transaction has committed.
            acknowledge(message);
            if (Boolean.TRUE.equals(processed)) {
                logger.info("Processed {} for {} (eventId={})", eventType, mortgageExternalId, eventId);
                return Outcome.PROCESSED;
            }
            logger.info("Duplicate {} eventId={} acknowledged without side effects", eventType, eventId);
            return Outcome.DUPLICATE;
        } catch (Exception e) {
            if (receiveCount >= maxReceiveCount) {
                logger.error("Servicing event failed on final attempt {}/{}; SQS will move messageId={} to the DLQ: {}",
                        receiveCount, maxReceiveCount, message.messageId(), e.getMessage(), e);
            } else {
                logger.error("Servicing event failed on attempt {}/{}; messageId={} left on queue for retry: {}",
                        receiveCount, maxReceiveCount, message.messageId(), e.getMessage(), e);
            }
            return Outcome.FAILED;
        } finally {
            MDC.remove("correlationId");
            MDC.remove("eventId");
        }
    }

    private JsonNode parseEnvelope(String body) throws Exception {
        JsonNode node = objectMapper.readTree(body);
        // Supports both raw delivery (RawMessageDelivery=true) and the SNS JSON wrapper.
        if (node.hasNonNull("Message") && node.hasNonNull("TopicArn")) {
            return objectMapper.readTree(node.get("Message").asText());
        }
        return node;
    }

    private static String requiredText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull() || value.asText().isBlank()) {
            throw new IllegalArgumentException("Event is missing required field " + field);
        }
        return value.asText();
    }

    private static int receiveCount(Message message) {
        Map<String, String> attributes = message.attributesAsStrings();
        String count = attributes == null ? null : attributes.get("ApproximateReceiveCount");
        try {
            return count == null ? 1 : Integer.parseInt(count);
        } catch (NumberFormatException e) {
            return 1;
        }
    }

    private void upsertDelinquencySnapshot(UUID mortgageId, JsonNode payload) {
        jdbcTemplate.update("""
                INSERT INTO delinquency (mortgage_id, delinquent_since, days_past_due, severity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (mortgage_id) DO UPDATE SET
                    delinquent_since = EXCLUDED.delinquent_since,
                    days_past_due = EXCLUDED.days_past_due,
                    severity = EXCLUDED.severity
                """,
                mortgageId,
                Date.valueOf(LocalDate.parse(requiredText(payload, "delinquentSince"))),
                payload.path("daysPastDue").asInt(),
                payload.path("severity").asText("MODERATE"));
    }

    static String describeEvent(String eventType, JsonNode payload) {
        return switch (eventType) {
            case "MortgageCreated" -> "Mortgage created for " + payload.path("borrowerExternalId").asText()
                    + " with original amount " + payload.path("originalAmount").asText();
            case "LoanApproved" -> "Loan " + payload.path("loanExternalId").asText() + " approved by "
                    + payload.path("approvedByRole").asText();
            case "PaymentReceived" -> "Payment " + payload.path("paymentAmount").asText() + " posted; balance now "
                    + payload.path("outstandingBalanceAfter").asText();
            case "PaymentMissed" -> "Payment due " + payload.path("dueDate").asText() + " missed; "
                    + payload.path("daysPastDue").asText() + " days past due";
            case "LoanDelinquent" -> "Delinquency assigned (" + payload.path("severity").asText() + "); "
                    + payload.path("daysPastDue").asText() + " days past due since " + payload.path("delinquentSince").asText();
            default -> "Processed event " + eventType;
        };
    }

    private void acknowledge(Message message) {
        sqsClient.deleteMessage(DeleteMessageRequest.builder()
                .queueUrl(queueUrl)
                .receiptHandle(message.receiptHandle())
                .build());
    }
}
