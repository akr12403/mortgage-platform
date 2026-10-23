package com.capstone.mortgage.security;

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
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

import com.nimbusds.jose.jwk.source.ImmutableSecret;

import javax.crypto.SecretKey;

/**
 * Stateless JWT security for mortgage-service (M6 Task 6.1).
 *
 * Public: GET /actuator/health/**, /actuator/info, POST /api/v1/auth/login.
 * RBAC (Task 6.2): role rules are enforced here, at the URL level, so they run BEFORE request parsing/validation
 * (a wrong role always gets 403, never a 400 that reveals validation details). Any route without an explicit
 * rule is denied (secure default). Matrix: docs/security/security-controls.md.
 * CSRF is disabled because the API is stateless: no cookies or server sessions are used, the token travels in the
 * Authorization header (which a cross-site form cannot set), so there is no ambient credential for CSRF to abuse.
 * @EnableMethodSecurity stays on so finer-grained @PreAuthorize checks can be layered on later (e.g. ownership).
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
@EnableConfigurationProperties(JwtProperties.class)
public class SecurityConfig {

    @Bean
    public SecretKey jwtSigningKey(JwtProperties properties) {
        return JwtKeys.signingKey(properties);
    }

    @Bean
    public JwtDecoder jwtDecoder(SecretKey jwtSigningKey, JwtProperties properties) {
        return JwtKeys.decoder(jwtSigningKey, properties);
    }

    @Bean
    public JwtEncoder jwtEncoder(SecretKey jwtSigningKey) {
        return new NimbusJwtEncoder(new ImmutableSecret<>(jwtSigningKey));
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http, JwtDecoder jwtDecoder, ObjectMapper objectMapper)
            throws Exception {
        SecurityErrorWriter errorWriter = new SecurityErrorWriter(objectMapper);
        http
                .csrf(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .headers(headers -> headers
                        .contentTypeOptions(c -> {})
                        .frameOptions(f -> f.deny())
                        .referrerPolicy(r -> r.policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER)))
                .exceptionHandling(e -> e.authenticationEntryPoint(errorWriter).accessDeniedHandler(errorWriter))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/actuator/health", "/actuator/health/**", "/actuator/info").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/v1/auth/login").permitAll()
                        .requestMatchers("/error").permitAll()
                        // Origination / underwriting
                        .requestMatchers(HttpMethod.POST, "/api/v1/borrowers").hasAnyRole(Rbac.ORIGINATION)
                        .requestMatchers(HttpMethod.POST, "/api/v1/mortgages").hasAnyRole(Rbac.ORIGINATION)
                        .requestMatchers(HttpMethod.POST, "/api/v1/mortgages/*/underwriting-decision").hasAnyRole(Rbac.ORIGINATION)
                        // Servicing writes
                        .requestMatchers(HttpMethod.POST, "/api/v1/mortgages/*/payments").hasAnyRole(Rbac.SERVICING_WRITE)
                        .requestMatchers(HttpMethod.POST, "/api/v1/delinquency-evaluations").hasAnyRole(Rbac.SERVICING_WRITE)
                        // Reads
                        .requestMatchers(HttpMethod.GET, "/api/v1/borrowers/*").hasAnyRole(Rbac.BORROWER_PII_READ)
                        .requestMatchers(HttpMethod.GET, "/api/v1/mortgages", "/api/v1/mortgages/*", "/api/v1/mortgages/*/payments")
                            .hasAnyRole(Rbac.ALL_ROLES)
                        // Secure default: anything not listed above is refused
                        .anyRequest().denyAll())
                .addFilterBefore(new JwtAuthenticationFilter(jwtDecoder, errorWriter), UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
