# System Context (C4 Level 1)

## Overview
The Enterprise Mortgage Platform provides core loan origination, servicing management, delinquency tracking, automated underwriting support, portfolio analytics, and AI-driven document intelligence. This C4 Level 1 context diagram outlines the platform's interaction boundaries with internal user personas and external enterprise dependencies.

## C4 Context Diagram

```mermaid
graph TD
    %% User Personas
    subgraph Users ["Platform Users"]
        UW[Underwriter]
        SA[Servicing Agent]
        RA[Risk Analyst]
        ADM[System Administrator]
        SEC[Security Analyst]
        ENG[Support Engineer]
    end

    %% Main System Boundary
    subgraph Platform ["Enterprise Mortgage Platform"]
        EMP[Mortgage Intelligence & Servicing Platform]
    end

    %% External Systems
    subgraph External ["External Integration Placeholders"]
        IDP[Identity Provider / IdP\n(Keycloak / Okta Placeholder)]
        EXT_S3[Cloud Object Storage\n(AWS S3 / Local MinIO Placeholder)]
        OBS[Observability Suite\n(Prometheus / Grafana / CloudWatch Placeholder)]
    end

    %% User Interactions
    UW -->|Evaluates loan risk & queries policy| EMP
    SA -->|Manages servicing & logs payments| EMP
    RA -->|Monitors yield & delinquency trends| EMP
    ADM -->|Configures RBAC & manages users| EMP
    SEC -->|Reviews audit trails & threat logs| EMP
    ENG -->|Monitors system health & runbooks| EMP

    %% External System Interactions
    EMP -->|Authenticates tokens via OIDC/OAuth2| IDP
    EMP -->|Stores & retrieves uploaded documents| EXT_S3
    EMP -->|Exports metrics, traces, & audit logs| OBS