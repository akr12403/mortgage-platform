package com.capstone.servicing.security;

import org.springframework.security.core.AuthenticationException;

/** A Bearer token was supplied but is malformed, tampered with, expired, or from the wrong issuer. */
public class InvalidTokenException extends AuthenticationException {
    public InvalidTokenException(String message, Throwable cause) {
        super(message, cause);
    }
}
