package com.capstone.servicing.configuration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.SqsClientBuilder;

import java.net.URI;

/**
 * SQS client. Credentials come from the default AWS provider chain at runtime (never hardcoded);
 * AWS_ENDPOINT_URL is set only for LocalStack.
 */
@Configuration
public class AwsSqsConfig {

    @Value("${aws.endpoint-url:}")
    private String endpointUrl;

    @Value("${aws.region:us-east-1}")
    private String region;

    @Bean
    public SqsClient sqsClient() {
        SqsClientBuilder builder = SqsClient.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create());
        if (endpointUrl != null && !endpointUrl.isBlank()) {
            builder.endpointOverride(URI.create(endpointUrl));
        }
        return builder.build();
    }
}
