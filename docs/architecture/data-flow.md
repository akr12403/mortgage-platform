## Overview
This document traces the request execution path for a mortgage document upload scenario (`income-proof.pdf`), illustrating network transmission, TLS termination points, application processing, and secure persistence in object storage and database tiers.

## Document Upload Sequence Trace

```mermaid
sequenceDiagram
    autonumber
    actor Client as Browser / API Client
    participant ALB as Ingress / Load Balancer (DMZ)
    participant MS as Mortgage Service (App Tier)
    participant DB as PostgreSQL Database (Data Tier)
    participant S3 as Object Storage (S3)

    Client->>ALB: 1. POST /loans/1001/documents/income-proof.pdf (HTTPS 443)
    Note over ALB: TLS Terminated at ALB; WAF Inspects Request Payload
    ALB->>MS: 2. Forward Request to App Container (HTTP/TLS 8080)
    Note over MS: Validates JWT Token & Performs PII Redaction/Sanitization
    MS->>DB: 3. Query Loan Status (JDBC/SQL - Port 5432)
    DB-->>MS: 4. Return Loan State (ACTIVE / UNDERWRITING)
    MS->>S3: 5. Write Encrypted Document Object (HTTPS / S3 API)
    S3-->>MS: 6. Return S3 Object Key & ETag
    MS->>DB: 7. Insert Document Metadata Record (SQL Insert)
    DB-->>MS: 8. Confirm Metadata Transaction Commited
    MS-->>ALB: 9. HTTP 201 Created Response JSON
    ALB-->>Client: 10. HTTP 201 Created (Encrypted HTTPS Response)