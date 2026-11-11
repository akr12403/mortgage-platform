package com.capstone.mortgage.events;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.Set;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * Producer-side contract test: every event this service publishes must validate against the
 * JSON Schema in docs/architecture/events/. Run from the repo with the docs folder available
 * (skipped when only the service folder is mounted).
 */
class EventSchemaContractTest {

    private static final Path SCHEMA_DIR = Path.of("..", "..", "docs", "architecture", "events");

    private final ObjectMapper objectMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    static Stream<Arguments> producedEvents() {
        return Stream.of(
                Arguments.of("mortgage-created.schema.json", EventEnvelope.wrap("MortgageCreated", null,
                        new EventPayloads.MortgageCreatedPayload("MTG-1010", "BOR-001", new BigDecimal("320000.00"), "PENDING"))),
                Arguments.of("loan-approved.schema.json", EventEnvelope.wrap("LoanApproved", null,
                        new EventPayloads.LoanApprovedPayload("MTG-1010", "LOAN-2010", "APPROVED", "UNDERWRITER"))),
                Arguments.of("payment-received.schema.json", EventEnvelope.wrap("PaymentReceived", null,
                        new EventPayloads.PaymentReceivedPayload("MTG-1001", new BigDecimal("1850.00"),
                                LocalDate.parse("2026-03-02"), new BigDecimal("317650.00")))),
                Arguments.of("payment-missed.schema.json", EventEnvelope.wrap("PaymentMissed", null,
                        new EventPayloads.PaymentMissedPayload("MTG-1002", LocalDate.parse("2026-01-01"), 31))),
                Arguments.of("loan-delinquent.schema.json", EventEnvelope.wrap("LoanDelinquent", null,
                        new EventPayloads.LoanDelinquentPayload("MTG-1002", "2026-01-31", 45, "MODERATE")))
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("producedEvents")
    void producedEventMatchesPublishedSchema(String schemaFile, EventEnvelope<?> envelope) throws Exception {
        Path schemaPath = SCHEMA_DIR.resolve(schemaFile);
        assumeTrue(Files.exists(schemaPath), "Schema docs not mounted; run from the repository checkout");

        JsonSchemaFactory factory = JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012);
        JsonSchema schema;
        try (InputStream in = Files.newInputStream(schemaPath)) {
            schema = factory.getSchema(in);
        }
        JsonNode event = objectMapper.readTree(objectMapper.writeValueAsString(envelope));

        Set<ValidationMessage> errors = schema.validate(event);
        assertThat(errors).as("Validation errors for %s: %s", schemaFile, errors).isEmpty();
    }
}
