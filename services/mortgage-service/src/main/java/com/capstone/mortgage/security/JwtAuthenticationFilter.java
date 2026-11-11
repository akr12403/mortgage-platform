package com.capstone.mortgage.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * Validates "Authorization: Bearer <jwt>" (signature, exp, iss) and populates the SecurityContext with
 * ROLE_<role> authorities from the "roles" claim. Registered before UsernamePasswordAuthenticationFilter.
 * No header → request continues unauthenticated (protected routes then return 401 via the entry point).
 * Tokens are never logged.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(JwtAuthenticationFilter.class);
    private static final String BEARER_PREFIX = "Bearer ";
    static final String MDC_USER_KEY = "user";

    private final JwtDecoder jwtDecoder;
    private final AuthenticationEntryPoint entryPoint;

    public JwtAuthenticationFilter(JwtDecoder jwtDecoder, AuthenticationEntryPoint entryPoint) {
        this.jwtDecoder = jwtDecoder;
        this.entryPoint = entryPoint;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.regionMatches(true, 0, BEARER_PREFIX, 0, BEARER_PREFIX.length())) {
            chain.doFilter(request, response);
            return;
        }

        Jwt jwt;
        try {
            jwt = jwtDecoder.decode(header.substring(BEARER_PREFIX.length()).trim());
        } catch (JwtException e) {
            SecurityContextHolder.clearContext();
            log.warn("Rejected bearer token: {}", e.getClass().getSimpleName());
            entryPoint.commence(request, response, new InvalidTokenException("Invalid bearer token", e));
            return;
        }

        List<String> roles = jwt.getClaimAsStringList("roles");
        List<GrantedAuthority> authorities = roles == null ? List.of() : roles.stream()
                .map(role -> (GrantedAuthority) new SimpleGrantedAuthority("ROLE_" + role))
                .toList();
        UsernamePasswordAuthenticationToken authentication =
                UsernamePasswordAuthenticationToken.authenticated(jwt.getSubject(), jwt, authorities);
        SecurityContextHolder.getContext().setAuthentication(authentication);

        MDC.put(MDC_USER_KEY, jwt.getSubject());
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_USER_KEY);
        }
    }
}
