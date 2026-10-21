package com.capstone.mortgage.service;

import com.capstone.mortgage.events.EventEnvelope;
import com.capstone.mortgage.events.EventPayloads;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.slf4j.MDC;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.PublishRequest;
import software.amazon.awssdk.services.sns.model.PublishResponse;
import software.amazon.awssdk.services.sns.model.SnsException;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class EventPublisherServiceTest {

    private static final String TOPIC = "arn:aws:sns:us-east-1:000000000000:capstone-mortgage-lifecycle-dev";

    private final SnsClient snsClient = mock(SnsClient.class);
    private final ObjectMapper objectMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    private final EventPublisherService publisher = new EventPublisherService(snsClient, objectMapper, TOPIC);

    @AfterEach
    void cleanUp() {
        MDC.clear();
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.clearSynchronization();
        }
    }

    @Test
    void publishesEnvelopeWithCorrelationIdFromHttpContext() throws Exception {
        when(snsClient.publish(any(PublishRequest.class))).thenReturn(PublishResponse.builder().messageId("m-1").build());
        MDC.put("correlationId", "7c9e6679-7425-40de-944b-e07fc1f90ae7");

        EventEnvelope<?> envelope = publisher.publishEvent("MortgageCreated",
                new EventPayloads.MortgageCreatedPayload("MTG-1010", "BOR-001", new BigDecimal("320000.00"), "PENDING"));

        ArgumentCaptor<PublishRequest> captor = ArgumentCaptor.forClass(PublishRequest.class);
        verify(snsClient).publish(captor.capture());
        PublishRequest request = captor.getValue();
        JsonNode body = objectMapper.readTree(request.message());

        assertThat(request.topicArn()).isEqualTo(TOPIC);
        assertThat(body.get("eventId").asText()).isEqualTo(envelope.eventId());
        assertThat(UUID.fromString(body.get("eventId").asText())).isNotNull();
        assertThat(body.get("eventType").asText()).isEqualTo("MortgageCreated");
        assertThat(body.get("schemaVersion").asText()).isEqualTo("1.0");
        assertThat(body.get("correlationId").asText()).isEqualTo("7c9e6679-7425-40de-944b-e07fc1f90ae7");
        assertThat(body.get("occurredAt").asText()).endsWith("Z");
        assertThat(body.at("/payload/mortgageExternalId").asText()).isEqualTo("MTG-1010");
        assertThat(request.messageAttributes().get("eventType").stringValue()).isEqualTo("MortgageCreated");
    }

    @Test
    void defersPublishUntilTransactionCommits() {
        when(snsClient.publish(any(PublishRequest.class))).thenReturn(PublishResponse.builder().messageId("m-2").build());
        TransactionSynchronizationManager.initSynchronization();

        publisher.publishEvent("PaymentMissed", new EventPayloads.PaymentMissedPayload("MTG-1002", null, 31));
        verifyNoInteractions(snsClient);

        for (TransactionSynchronization sync : TransactionSynchronizationManager.getSynchronizations()) {
            sync.afterCommit();
        }
        verify(snsClient, times(1)).publish(any(PublishRequest.class));
    }

    @Test
    void doesNotPublishWhenTransactionRollsBack() {
        TransactionSynchronizationManager.initSynchronization();

        publisher.publishEvent("PaymentMissed", new EventPayloads.PaymentMissedPayload("MTG-1002", null, 31));
        for (TransactionSynchronization sync : TransactionSynchronizationManager.getSynchronizations()) {
            sync.afterCompletion(TransactionSynchronization.STATUS_ROLLED_BACK);
        }
        verifyNoInteractions(snsClient);
    }

    @Test
    void snsFailureIsLoggedNotThrown() {
        when(snsClient.publish(any(PublishRequest.class))).thenThrow(SnsException.builder().message("boom").build());

        assertThatCode(() -> publisher.publishEvent("PaymentMissed",
                new EventPayloads.PaymentMissedPayload("MTG-1002", null, 31))).doesNotThrowAnyException();
    }

    @Test
    void generatesCorrelationIdWhenNoneInContext() throws Exception {
        when(snsClient.publish(any(PublishRequest.class))).thenReturn(PublishResponse.builder().messageId("m-3").build());

        EventEnvelope<?> envelope = publisher.publishEvent("PaymentMissed",
                new EventPayloads.PaymentMissedPayload("MTG-1002", null, 31));

        assertThat(UUID.fromString(envelope.correlationId())).isNotNull();
    }
}
