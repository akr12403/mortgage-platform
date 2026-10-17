package com.capstone.mortgage.configuration; // Updated to match your folder name

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sns.SnsClient;

import java.net.URI;

@Configuration
public class AwsConfig {

    @Value("${aws.endpoint-url:http://localhost:4566}")
    private String endpointUrl;

    @Value("${aws.region:us-east-1}")
    private String region;

    @Bean
    public SnsClient snsClient() {
        return SnsClient.builder()
                .region(Region.of(region))
                .endpointOverride(URI.create(endpointUrl))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .build();
    }
}