package com.capstone.servicing.controller;

import com.capstone.servicing.security.SecurityConfig;
import com.capstone.servicing.service.ServicingService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** M9 Task 9.3: JSON log lines and the per-request http_request line (docs/operations/observability.md). */
@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
@WithMockUser(username = "servicing@capstone.local", roles = "SERVICING_AGENT")
@ExtendWith(OutputCaptureExtension.class)
class RequestLoggingTest {

    private static final String CID = "test-corr-0123456789";
    private static final ObjectMapper JSON = new ObjectMapper();

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ServicingService servicingService;

    @Test
    void requestLineHasRouteTemplateStatusDurationAndCorrelationId(CapturedOutput output) throws Exception {
        when(servicingService.getServicingHistory("MTG-9999")).thenReturn(java.util.Collections.emptyList());

        int actual = mockMvc.perform(get("/api/v1/mortgages/MTG-9999/servicing-history").header("X-Correlation-ID", CID))
                .andReturn().getResponse().getStatus();

        Map<String, Object> line = requestLines(output).stream()
                .filter(l -> CID.equals(l.get("correlationId")))
                .findFirst().orElseThrow(() -> new AssertionError("no http_request line in:\n" + output.getOut()));
        assertThat(line.get("service.name")).isEqualTo("servicing-service");
        assertThat(line.get("log.level")).isEqualTo("INFO");
        assertThat(line.get("http.method")).isEqualTo("GET");
        assertThat(line.get("http.route")).isEqualTo("/api/v1/mortgages/{id}/servicing-history"); // never MTG-9999
        assertThat(((Number) line.get("http.status")).intValue()).isEqualTo(actual);
        assertThat(((Number) line.get("durationMs")).doubleValue()).isGreaterThanOrEqualTo(0.0);
    }

    @Test
    void healthChecksAreNotRequestTraffic(CapturedOutput output) throws Exception {
        mockMvc.perform(get("/actuator/health"));
        assertThat(requestLines(output)).isEmpty();
    }

    /** JSON lines on stdout whose message is http_request, with nested objects flattened to dotted keys. */
    static List<Map<String, Object>> requestLines(CapturedOutput output) throws Exception {
        List<Map<String, Object>> lines = new ArrayList<>();
        for (String raw : output.getOut().split("\\R")) {
            if (!raw.startsWith("{")) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> doc = JSON.readValue(raw, Map.class);
            Map<String, Object> flat = new LinkedHashMap<>();
            flatten("", doc, flat);
            if ("http_request".equals(flat.get("message"))) {
                lines.add(flat);
            }
        }
        return lines;
    }

    @SuppressWarnings("unchecked")
    private static void flatten(String prefix, Map<String, Object> in, Map<String, Object> out) {
        in.forEach((key, value) -> {
            String name = prefix.isEmpty() ? key : prefix + "." + key;
            if (value instanceof Map<?, ?> nested) {
                flatten(name, (Map<String, Object>) nested, out);
            } else {
                out.put(name, value);
            }
        });
    }
}
