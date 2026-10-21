package com.capstone.mortgage.service;

import com.capstone.mortgage.events.EventEnvelope;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.MessageAttributeValue;
import software.amazon.awssdk.services.sns.model.PublishRequest;

import java.util.Map;

/**
 * Publishes mortgage lifecycle events to the SNS topic.
 *
 * Events are built immediately (so they capture the HTTP correlation ID from MDC) but are only
 * sent to SNS after the surrounding database transaction commits. This prevents consumers from
 * seeing events for writes that were rolled back.
 */
@Service
public class EventPublisherService {

    private static final Logger log = LoggerFactory.getLogger(EventPublisherService.class);
    static final String MDC_CORRELATION_ID_KEY = "correlationId";

    private final SnsClient snsClient;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public EventPublisherService(
            SnsClient snsClient,
            ObjectMapper objectMapper,
            @Value("${aws.sns.topic-arn}") String topicArn) {
        this.snsClient = snsClient;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    /**
     * Wraps the payload in the standard envelope and publishes it after commit
     * (or immediately when no transaction is active).
     */
    public <T> EventEnvelope<T> publishEvent(String eventType, T payload) {
        EventEnvelope<T> envelope = EventEnvelope.wrap(eventType, MDC.get(MDC_CORRELATION_ID_KEY), payload);

        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    send(envelope);
                }
            });
        } else {
            send(envelope);
        }
        return envelope;
    }

    void send(EventEnvelope<?> envelope) {
        String previousCorrelationId = MDC.get(MDC_CORRELATION_ID_KEY);
        MDC.put(MDC_CORRELATION_ID_KEY, envelope.correlationId());
        try {
            String messageJson = objectMapper.writeValueAsString(envelope);
            PublishRequest request = PublishRequest.builder()
                    .topicArn(topicArn)
                    .message(messageJson)
                    .messageAttributes(Map.of(
                            "eventType", stringAttribute(envelope.eventType()),
                            "schemaVersion", stringAttribute(envelope.schemaVersion()),
                            "correlationId", stringAttribute(envelope.correlationId())
                    ))
                    .build();

            String messageId = snsClient.publish(request).messageId();
            log.info("Published {} eventId={} snsMessageId={}", envelope.eventType(), envelope.eventId(), messageId);
        } catch (JsonProcessingException e) {
            log.error("Could not serialize {} eventId={}", envelope.eventType(), envelope.eventId(), e);
        } catch (RuntimeException e) {
            // The business transaction has already committed; surface loudly for operators.
            log.error("Failed to publish {} eventId={} to SNS topic {}",
                    envelope.eventType(), envelope.eventId(), topicArn, e);
        } finally {
            if (previousCorrelationId == null) {
                MDC.remove(MDC_CORRELATION_ID_KEY);
            } else {
                MDC.put(MDC_CORRELATION_ID_KEY, previousCorrelationId);
            }
        }
    }

    private static MessageAttributeValue stringAttribute(String value) {
        return MessageAttributeValue.builder().dataType("String").stringValue(value).build();
    }
}
