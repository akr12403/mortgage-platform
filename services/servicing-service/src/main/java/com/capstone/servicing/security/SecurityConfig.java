package com.capstone.servicing.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.header.writers.CrossOriginResourcePolicyHeaderWriter;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.header.writers.StaticHeadersWriter;

import java.time.Clock;

/**
 * Stateless JWT validation for servicing-service (resource server only). Tokens are issued by mortgage-service
 * (POST /api/v1/auth/login). Public: GET /actuator/health/**, /actuator/info.
 * RBAC (Task 6.2) is enforced here at the URL level (before request validation); unlisted routes are denied.
 * Matrix: docs/security/security-controls.md.
 * CSRF disabled: stateless bearer-token API with no cookies or sessions (see docs/security/authentication.md).
 * The SQS consumer is not an HTTP endpoint and is unaffected.
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
@EnableConfigurationProperties({JwtProperties.class, RateLimitProperties.class})
public class SecurityConfig {

    @Bean
    public JwtDecoder jwtDecoder(JwtProperties properties) {
        return JwtKeys.decoder(JwtKeys.signingKey(properties), properties);
    }

    @Bean
    public RateLimiter rateLimiter() {
        return new RateLimiter(Clock.systemUTC());
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http, JwtDecoder jwtDecoder, ObjectMapper objectMapper,
                                                   RateLimiter rateLimiter, RateLimitProperties rateLimitProperties)
            throws Exception {
        SecurityErrorWriter errorWriter = new SecurityErrorWriter(objectMapper);
        http
                .csrf(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Security headers (Task 6.3); same baseline as mortgage-service. HSTS is sent on HTTPS only.
                .headers(headers -> headers
                        .contentTypeOptions(c -> {})
                        .frameOptions(f -> f.deny())
                        .referrerPolicy(r -> r.policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
                        .contentSecurityPolicy(csp -> csp.policyDirectives(SecurityHeaders.CONTENT_SECURITY_POLICY))
                        // permissionsPolicy(Customizer) returns PermissionsPolicyConfig in Spring Security 6.2, so add it as a plain writer
                        .addHeaderWriter(new StaticHeadersWriter("Permissions-Policy", SecurityHeaders.PERMISSIONS_POLICY))
                        .crossOriginResourcePolicy(c -> c.policy(
                                CrossOriginResourcePolicyHeaderWriter.CrossOriginResourcePolicy.SAME_ORIGIN))
                        .httpStrictTransportSecurity(hsts -> hsts.includeSubDomains(true).maxAgeInSeconds(31_536_000)))
                .exceptionHandling(e -> e.authenticationEntryPoint(errorWriter).accessDeniedHandler(errorWriter))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/actuator/health", "/actuator/health/**", "/actuator/info").permitAll()
                        .requestMatchers("/error").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/v1/mortgages/*/servicing-history", "/api/v1/mortgages/*/delinquency")
                            .hasAnyRole(Rbac.ALL_ROLES)
                        .requestMatchers(HttpMethod.POST, "/api/v1/mortgages/*/servicing-events").hasAnyRole(Rbac.SERVICING_WRITE)
                        // Secure default: anything not listed above is refused
                        .anyRequest().denyAll())
                .addFilterBefore(new JwtAuthenticationFilter(jwtDecoder, errorWriter), UsernamePasswordAuthenticationFilter.class)
                .addFilterAfter(new RateLimitFilter(rateLimiter, rateLimitProperties, errorWriter), UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
