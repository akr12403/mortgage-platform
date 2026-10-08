## Overview
The platform deployment model establishes strict isolation between internet-facing edge routing, private application microservices, and secured data persistence stores.

## Environments
- **`dev` (Development)**: Local developer workstations executing containerized microservices via Docker Compose on macOS (ARM64) / Windows sandbox environments.
- **`test` (Staging / QA)**: CI/CD-integrated test environment performing automated integration, security scanning, and E2E regression tests.
- **`prod` (Production)**: High-availability cloud deployment across multi-AZ private subnets with managed database clusters and zero-trust perimeter enforcement.

## Deployment Topology Diagram

```mermaid
graph TB
    subgraph Internet ["Untrusted Internet (Zone 0)"]
        CLIENT[Browser / API Client]
    end

    subgraph EdgeZone ["DMZ / Edge Security (Zone 1)"]
        DNS[Route 53 / DNS]
        WAF[AWS WAF / Perimeter Firewall]
        ALB[Public Load Balancer / Ingress Router]
    end

    subgraph AppZone ["Private Application Tier (Zone 2 & Zone 3)"]
        MS[Mortgage Service]
        SS[Servicing Service]
        AS[Mortgage Analytics Service]
        AI[AI Knowledge Assistant\n(Zone 3 - High Sensitivity)]
    end

    subgraph DataZone ["Private Data Tier (Zone 4)"]
        DB[(PostgreSQL / RDS\n:5432)]
        VDB[(Vector Database)]
        S3[(AWS S3 / Object Storage)]
    end

    %% Network Flow & Boundaries
    CLIENT ==>|HTTPS / Port 443| DNS
    DNS --> WAF
    WAF --> ALB

    %% Boundary Line 1: Internet to Edge
    ALB ==>|TLS Termination / Forward to App Port| MS
    ALB ==>|TLS Termination / Forward to App Port| SS
    ALB ==>|TLS Termination / Forward to App Port| AS
    ALB ==>|TLS Termination / Forward to App Port| AI

    %% Boundary Line 2: App to Data
    MS -->|Private DB Subnet / TLS| DB
    SS -->|Private DB Subnet / TLS| DB
    AS -->|Private Read-Only DB Subnet / TLS| DB
    AI -->|Private Vector Queries| VDB
    MS -->|Private VPC Endpoint / HTTPS| S3