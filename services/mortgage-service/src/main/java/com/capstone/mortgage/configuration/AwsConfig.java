package com.capstone.mortgage.configuration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.SnsClientBuilder;

import java.net.URI;

/**
 * SNS client configuration.
 *
 * Credentials are never hardcoded: the default AWS provider chain reads them at runtime
 * (env vars AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, AWS_PROFILE, or an IAM role).
 * AWS_ENDPOINT_URL is only set for LocalStack; leave it empty to talk to real AWS.
 */
@Configuration
public class AwsConfig {

    @Value("${aws.endpoint-url:}")
    private String endpointUrl;

    @Value("${aws.region:us-east-1}")
    private String region;

    @Bean
    public SnsClient snsClient() {
        SnsClientBuilder builder = SnsClient.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create());
        if (endpointUrl != null && !endpointUrl.isBlank()) {
            builder.endpointOverride(URI.create(endpointUrl));
        }
        return builder.build();
    }
}
