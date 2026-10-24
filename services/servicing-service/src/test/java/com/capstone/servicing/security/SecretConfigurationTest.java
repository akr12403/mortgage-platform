package com.capstone.servicing.security;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * M6 Task 6.6 regression test for DP-GAP-2: secrets must have no fallback value in application.yml, so a missing
 * secret stops startup instead of silently using a guessable default.
 */
class SecretConfigurationTest {

    @Test
    void secretsHaveNoDefaultsInApplicationYml() throws IOException {
        String yml;
        try (InputStream in = getClass().getResourceAsStream("/application.yml")) {
            assertThat(in).as("application.yml on the classpath").isNotNull();
            yml = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        assertThat(yml).contains("${POSTGRES_PASSWORD}");
        // An empty default (${JWT_SECRET:}) is fine: JwtKeys then rejects the empty/short value at startup.
        // A non-empty default would be a real fallback secret.
        assertThat(yml).doesNotContainPattern("\\$\\{(POSTGRES_PASSWORD|JWT_SECRET|AUTH_SEED_PASSWORD):[^}]");
    }
}
