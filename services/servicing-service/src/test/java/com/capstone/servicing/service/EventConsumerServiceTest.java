package com.capstone.servicing.service;

import com.capstone.servicing.entity.EventInbox;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.exception.ResourceNotFoundException;
import com.capstone.servicing.repository.EventInboxRepository;
import com.capstone.servicing.repository.ServicingHistoryRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.MessageSystemAttributeName;

import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class EventConsumerServiceTest {

    private static final String QUEUE = "http://localstack:4566/000000000000/capstone-mortgage-servicing-dev";
    private static final UUID MORTGAGE_UUID = UUID.fromString("11111111-2222-3333-4444-555555555555");

    private final SqsClient sqsClient = mock(SqsClient.class);
    private final ServicingHistoryRepository historyRepository = mock(ServicingHistoryRepository.class);
    private final EventInboxRepository inboxRepository = mock(EventInboxRepository.class);
    private final ServicingService servicingService = mock(ServicingService.class);
    private final TransactionTemplate transactionTemplate = mock(TransactionTemplate.class);
    private final JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    private EventConsumerService consumer;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        when(transactionTemplate.execute(any())).thenAnswer(invocation ->
                ((TransactionCallback<Object>) invocation.getArgument(0)).doInTransaction(null));
        when(servicingService.findMortgageId("MTG-1001")).thenReturn(MORTGAGE_UUID);
        when(servicingService.findMortgageId("MTG-0000")).thenThrow(ResourceNotFoundException.mortgage("MTG-0000"));
        consumer = new EventConsumerService(sqsClient, historyRepository, inboxRepository, new ObjectMapper(),
                servicingService, transactionTemplate, jdbcTemplate, QUEUE, 3, true);
    }

    private static String envelope(String eventId, String eventType, String schemaVersion, String payloadJson) {
        return """
                {"eventId":"%s","eventType":"%s","schemaVersion":"%s","occurredAt":"2026-03-15T14:30:00Z",
                 "correlationId":"7c9e6679-7425-40de-944b-e07fc1f90ae7","payload":%s}
                """.formatted(eventId, eventType, schemaVersion, payloadJson);
    }

    private static Message message(String body, int receiveCount) {
        return Message.builder()
                .messageId(UUID.randomUUID().toString())
                .receiptHandle("rh-" + receiveCount)
                .body(body)
                .attributes(Map.of(MessageSystemAttributeName.APPROXIMATE_RECEIVE_COUNT, Integer.toString(receiveCount)))
                .build();
    }

    private static final String PAYMENT_RECEIVED_PAYLOAD =
            "{\"mortgageExternalId\":\"MTG-1001\",\"paymentAmount\":1850.0,\"paidDate\":\"2026-03-02\",\"outstandingBalanceAfter\":317650.0}";

    @Test
    void paymentReceived_writesHistoryAndInbox_thenAcknowledges() {
        String eventId = UUID.randomUUID().toString();

        var outcome = consumer.processMessage(message(envelope(eventId, "PaymentReceived", "1.0", PAYMENT_RECEIVED_PAYLOAD), 1));

        assertThat(outcome).isEqualTo(EventConsumerService.Outcome.PROCESSED);
        ArgumentCaptor<ServicingHistory> history = ArgumentCaptor.forClass(ServicingHistory.class);
        verify(historyRepository).save(history.capture());
        assertThat(history.getValue().getEventType()).isEqualTo("PAYMENT_POSTED");
        assertThat(history.getValue().getMortgageId()).isEqualTo(MORTGAGE_UUID);
        ArgumentCaptor<EventInbox> inbox = ArgumentCaptor.forClass(EventInbox.class);
        verify(inboxRepository).save(inbox.capture());
        assertThat(inbox.getValue().getEventId()).isEqualTo(UUID.fromString(eventId));
        verify(sqsClient).deleteMessage(any(DeleteMessageRequest.class));
    }

    @Test
    void duplicateEventId_isAcknowledgedWithoutSideEffects() {
        String eventId = UUID.randomUUID().toString();
        when(inboxRepository.existsByEventId(UUID.fromString(eventId))).thenReturn(true);

        var outcome = consumer.processMessage(message(envelope(eventId, "PaymentReceived", "1.0", PAYMENT_RECEIVED_PAYLOAD), 1));

        assertThat(outcome).isEqualTo(EventConsumerService.Outcome.DUPLICATE);
        verify(historyRepository, never()).save(any());
        verify(sqsClient).deleteMessage(any(DeleteMessageRequest.class));
    }

    @Test
    void unknownMortgage_isNotAcknowledged_soSqsRetriesThenDeadLetters() {
        String body = envelope(UUID.randomUUID().toString(), "MortgageCreated", "1.0",
                "{\"mortgageExternalId\":\"MTG-0000\",\"borrowerExternalId\":\"BOR-001\",\"originalAmount\":100000.0,\"status\":\"PENDING\"}");

        assertThat(consumer.processMessage(message(body, 1))).isEqualTo(EventConsumerService.Outcome.FAILED);
        assertThat(consumer.processMessage(message(body, 3))).isEqualTo(EventConsumerService.Outcome.FAILED);
        verify(sqsClient, never()).deleteMessage(any(DeleteMessageRequest.class));
        verify(inboxRepository, never()).save(any());
    }

    @Test
    void malformedEnvelope_isNotAcknowledged() {
        assertThat(consumer.processMessage(message("{\"eventType\":\"PaymentReceived\"}", 1)))
                .isEqualTo(EventConsumerService.Outcome.FAILED);
        assertThat(consumer.processMessage(message("not json", 1)))
                .isEqualTo(EventConsumerService.Outcome.FAILED);
        verify(sqsClient, never()).deleteMessage(any(DeleteMessageRequest.class));
    }

    @Test
    void unsupportedSchemaMajorVersion_isNotAcknowledged() {
        String body = envelope(UUID.randomUUID().toString(), "PaymentReceived", "2.0", PAYMENT_RECEIVED_PAYLOAD);

        assertThat(consumer.processMessage(message(body, 1))).isEqualTo(EventConsumerService.Outcome.FAILED);
        verify(sqsClient, never()).deleteMessage(any(DeleteMessageRequest.class));
    }

    @Test
    void unknownEventType_isSkippedAndAcknowledged() {
        String body = envelope(UUID.randomUUID().toString(), "EscrowAnalyzed", "1.0", "{\"mortgageExternalId\":\"MTG-1001\"}");

        assertThat(consumer.processMessage(message(body, 1))).isEqualTo(EventConsumerService.Outcome.SKIPPED);
        verify(historyRepository, never()).save(any());
        verify(sqsClient).deleteMessage(any(DeleteMessageRequest.class));
    }

    @Test
    void loanDelinquent_alsoUpsertsDelinquencySnapshot() {
        String body = envelope(UUID.randomUUID().toString(), "LoanDelinquent", "1.0",
                "{\"mortgageExternalId\":\"MTG-1001\",\"delinquentSince\":\"2026-01-31\",\"daysPastDue\":45,\"severity\":\"MODERATE\"}");

        assertThat(consumer.processMessage(message(body, 1))).isEqualTo(EventConsumerService.Outcome.PROCESSED);
        verify(jdbcTemplate).update(contains("INSERT INTO delinquency"), eq(MORTGAGE_UUID),
                any(java.sql.Date.class), eq(45), eq("MODERATE"));
    }

    @Test
    void snsJsonWrapperIsUnwrapped() {
        String inner = envelope(UUID.randomUUID().toString(), "PaymentReceived", "1.0", PAYMENT_RECEIVED_PAYLOAD);
        String wrapped = "{\"Type\":\"Notification\",\"TopicArn\":\"arn:aws:sns:us-east-1:000000000000:capstone-mortgage-lifecycle-dev\",\"Message\":"
                + new com.fasterxml.jackson.databind.node.TextNode(inner).toString() + "}";

        assertThat(consumer.processMessage(message(wrapped, 1))).isEqualTo(EventConsumerService.Outcome.PROCESSED);
    }
}
