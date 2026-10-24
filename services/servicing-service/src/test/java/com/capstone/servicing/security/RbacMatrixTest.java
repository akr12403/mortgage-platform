package com.capstone.servicing.security;

import com.capstone.servicing.controller.ServicingController;
import com.capstone.servicing.dto.DelinquencyResponse;
import com.capstone.servicing.entity.ServicingHistory;
import com.capstone.servicing.service.ServicingService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** M6 Task 6.2: every servicing-service endpoint x all five roles (matrix in docs/security/security-controls.md). */
@WebMvcTest(ServicingController.class)
@ActiveProfiles("test")
@Import(SecurityConfig.class)
class RbacMatrixTest {

    record Endpoint(String name, HttpMethod method, String path, String body, Set<String> allowed) {
        @Override
        public String toString() {
            return name;
        }
    }

    static final List<Endpoint> ENDPOINTS = List.of(
            new Endpoint("GET servicing-history", HttpMethod.GET, "/api/v1/mortgages/MTG-1001/servicing-history", null, Set.of(Rbac.ALL_ROLES)),
            new Endpoint("GET delinquency", HttpMethod.GET, "/api/v1/mortgages/MTG-1002/delinquency", null, Set.of(Rbac.ALL_ROLES)),
            new Endpoint("POST servicing-events", HttpMethod.POST, "/api/v1/mortgages/MTG-1001/servicing-events",
                    "{\"eventType\":\"ESCROW_ANALYSIS\",\"description\":\"Annual escrow review\"}", Set.of(Rbac.SERVICING_WRITE))
    );

    static Stream<Arguments> endpointRoleMatrix() {
        List<Arguments> cases = new ArrayList<>();
        for (Endpoint endpoint : ENDPOINTS) {
            for (String role : Rbac.ALL_ROLES) {
                cases.add(Arguments.of(endpoint, role, endpoint.allowed().contains(role)));
            }
        }
        return cases.stream();
    }

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ServicingService servicingService;

    @BeforeEach
    void stub() {
        ServicingHistory note = new ServicingHistory();
        note.setEventType("ESCROW_ANALYSIS");
        note.setEventTime(Instant.now());
        when(servicingService.getServicingHistory("MTG-1001")).thenReturn(List.of());
        when(servicingService.getDelinquencyStatus("MTG-1002"))
                .thenReturn(new DelinquencyResponse("MTG-1002", "DELINQUENT", "2026-01-10", 45, "MODERATE"));
        when(servicingService.createServicingEvent(eq("MTG-1001"), anyString(), anyString())).thenReturn(note);
    }

    private MockHttpServletRequestBuilder build(Endpoint endpoint) {
        MockHttpServletRequestBuilder builder = request(endpoint.method(), endpoint.path());
        if (endpoint.body() != null) {
            builder.contentType(MediaType.APPLICATION_JSON).content(endpoint.body());
        }
        return builder;
    }

    @ParameterizedTest(name = "{0} as {1} -> allowed={2}")
    @MethodSource("endpointRoleMatrix")
    void roleMatrix(Endpoint endpoint, String role, boolean allowed) throws Exception {
        var result = mockMvc.perform(build(endpoint).with(user(role.toLowerCase() + "@capstone.local").roles(role)));
        if (allowed) {
            result.andExpect(status().is2xxSuccessful());
        } else {
            result.andExpect(status().isForbidden())
                    .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
        }
    }

    @Test
    void unmappedRouteIsDeniedByDefault() throws Exception {
        mockMvc.perform(request(HttpMethod.DELETE, "/api/v1/mortgages/MTG-1001/servicing-history")
                        .with(user("admin@capstone.local").roles(Rbac.ADMIN)))
                .andExpect(status().isForbidden());
    }
}
