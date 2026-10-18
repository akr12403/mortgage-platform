package com.capstone.mortgage.service;

import com.capstone.mortgage.events.EventEnvelope;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.MessageAttributeValue;
import software.amazon.awssdk.services.sns.model.PublishRequest;

import java.util.Map;

@Service
public class EventPublisherService {

    private final SnsClient snsClient;
    private final ObjectMapper objectMapper;

    @Value("${aws.sns.topic-arn:arn:aws:sns:us-east-1:000000000000:capstone-mortgage-lifecycle-dev}")
    private String topicArn;

    public EventPublisherService(SnsClient snsClient, ObjectMapper objectMapper) {
        this.snsClient = snsClient;
        this.objectMapper = objectMapper;
    }

    public void publishEvent(String eventType, Object payload) {
        try {
            // Automatically grab correlation ID from your CorrelationIdFilter MDC context
            String correlationId = MDC.get("correlationId");
            
            EventEnvelope<?> envelope = EventEnvelope.wrap(eventType, correlationId, payload);
            String messageJson = objectMapper.writeValueAsString(envelope);

            PublishRequest request = PublishRequest.builder()
                    .topicArn(topicArn)
                    .message(messageJson)
                    .messageAttributes(Map.of(
                            "eventType", MessageAttributeValue.builder()
                                    .dataType("String")
                                    .stringValue(eventType)
                                    .build()
                    ))
                    .build();

            snsClient.publish(request);
        } catch (Exception e) {
            throw new RuntimeException("Failed to publish event to SNS: " + eventType, e);
        }
    }
}