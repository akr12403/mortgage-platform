package com.capstone.mortgage.security;

/** Header values shared by the API services (M6 Task 6.3). */
public final class SecurityHeaders {

    private SecurityHeaders() {}

    /** JSON-only API: nothing may be loaded, framed, or submitted from a response. */
    public static final String CONTENT_SECURITY_POLICY =
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'";

    /** No browser features are needed by an API response. */
    public static final String PERMISSIONS_POLICY = "geolocation=(), camera=(), microphone=(), payment=(), usb=()";
}
