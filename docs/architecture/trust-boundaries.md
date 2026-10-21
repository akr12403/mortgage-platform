## Summary of Trust Boundaries

| Boundary ID | Crossing Description | Core Security Controls | Protocol & Port | Monitoring & Audit |
| --- | --- | --- | --- | --- |
| **TB-1** | Internet $\rightarrow$ Edge / DMZ | TLS 1.3 encryption, WAF signature inspection, IP rate-limiting. | HTTPS / Port 443 | WAF logs, CloudWatch access logs. |
| **TB-2** | DMZ / Edge $\rightarrow$ App Tier | Ingress routing, JWT Bearer Token validation, OAuth2/OIDC claims check. | HTTP/REST / Application Ports (8080-8083) | API Gateway route logs, distributed traces. |
| **TB-3** | App Tier $\rightarrow$ Private Data Tier | Security group authorization, database credentials via Secrets Manager, KMS key encryption. | JDBC / Port 5432 (SQL), HTTPS / Port 443 (S3 API) | PostgreSQL audit logs (pgaudit), S3 Data Plane Access Logs. |
| **TB-4** | App Tier $\rightarrow$ AI Knowledge Assistant | Strict prompt payload sanitization, zero PII propagation, isolated runtime container context. | HTTP/REST / Port 8083 | Prompt execution metrics, AI interaction logs. |

## Network Segmentation Rules
- **No Direct Database Access**: Database instances in Zone 4 must **never** possess public IP addresses or routes to the internet.
- **Least-Privilege IAM**: Microservices obtain short-lived cloud execution tokens granting access strictly to their required storage buckets and database secrets.
- **In-Transit Encryption**: All service-to-service traffic across trust boundaries requires TLS/mTLS protocol enforcement.