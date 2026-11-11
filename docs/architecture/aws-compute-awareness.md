# AWS Compute Awareness: Lambda, ECS, EKS, Glue, EMR (M8, Session 28/30)

This is an awareness note, not a deployment. In M8 the three services run in docker compose on a developer machine. Two pieces already run in AWS:
- the document processor runs on **Lambda**;
- the ETL runs on **Glue Python shell**.

This note records where each workload *would* run and why, so M9 (Terraform, CI/CD) starts from a decision.

## Where each workload runs

| Workload | Shape | M8 | Target (M9+) | Why |
| --- | --- | --- | --- | --- |
| `capstone-mortgage-doc-processor-dev` | Event-driven, short (≈ 0.7–3.6 s), bursty, no state | **Lambda** (python3.14, arm64, 256 MB) | Lambda | Pay per invocation and nothing to keep warm. The S3 trigger is native. |
| `mortgage-service` (Java, 8080) | Long-running HTTP API, JDBC pool, SNS publisher, ~1 s JVM start | compose | **ECS on Fargate** behind an ALB | A steady request stream, connection pooling and JVM warm-up suit a long-running container better than Lambda: cold starts and a database connection per invocation are a poor fit. Fargate means no servers to patch. |
| `servicing-service` (Java, 8081) | Long-running SQS consumer + HTTP | compose | **ECS on Fargate** (scaled on SQS backlog) | Long polling needs a process that stays up. It scales out on `ApproximateNumberOfMessagesVisible`. |
| `mortgage-analytics-service` (Python, 8000) | HTTP API + SQS consumer thread | compose (+ `compose-aws-up.sh` for S3/DynamoDB) | **ECS on Fargate** | Same reasons. One task definition with one task role (`mortgage-analytics-role`). |
| `mortgage-knowledge-assistant` (Python, 8001) | HTTP API calling an external LLM | compose | **ECS on Fargate** | Requests last seconds, and the outbound HTTPS needs a NAT gateway or a VPC endpoint plan |
| Delinquency ETL | Batch, small data (KBs today), about 12 s | **Glue Python shell** (0.0625 DPU) | Glue Python shell, then Glue **Spark** if the data grows | See the sizing table below |

### Why not EKS (Kubernetes)?

EKS adds a cluster control plane at about $73/month per cluster plus worker capacity, and then Kubernetes upgrades, add-ons, ingress controllers and IRSA/Pod Identity to look after. That pays off with many teams and services, multi-cloud portability, or a need for Kubernetes-native tooling such as operators, service mesh or Argo. With four services owned by one team, **ECS + Fargate** gives the same container isolation and per-task IAM roles with far less operating work. The decision should be revisited if the platform grows past roughly 15–20 services or adopts a company-wide Kubernetes standard.

### How the M8 IAM roles carry over

Each ECS service gets a **task role**: the same M8 role and the same policy, with only the trust policy changed to `ecs-tasks.amazonaws.com`. The SDKs then pick up rotating credentials from the container credentials endpoint automatically. `compose-aws-up.sh` and its 1-hour STS hand-off exist only because the services run locally ([aws-iam-matrix.md](aws-iam-matrix.md#how-workloads-get-credentials-no-access-keys)). A separate **task execution role** pulls images and writes logs. It never gets application data permissions.

## ETL sizing: Glue Python shell vs Glue Spark vs EMR

| Option | Good for | Cost model (us-east-2, 2026) | Switch when |
| --- | --- | --- | --- |
| **Glue Python shell** (current) | One-node jobs up to roughly 1 GB in memory (0.0625 DPU = 1 GB; 1 DPU = 16 GB) | $0.44 per DPU-hour, 1-minute minimum: **about $0.0005 per run today** | Input grows past about 1 GB, or the run approaches the 10-minute timeout |
| **Glue Spark job** (G.1X workers) | Distributed joins and aggregation over GBs to TBs, Parquet, Data Catalog, job bookmarks | $0.44 per DPU-hour per worker, minimum 2 workers, 1-minute minimum | The data no longer fits one node; incremental loads need bookmarks |
| **EMR** (on EC2, or EMR Serverless) | Long or very large Spark/Hive/Presto workloads, custom libraries, steady heavy usage, cluster tuning | EC2 instances plus the EMR uplift (on EC2), or vCPU-hour/GB-hour (Serverless) | Many TB a day, or jobs running for hours where tuning executors beats Glue's per-DPU price. **Out of scope for M8** (handbook). |

**For this portfolio:**
- 18 mortgages export to about 2 KB of CSV, so even 1 million mortgages (about 150 MB) stays within the Python shell job's 1 DPU option.
- The ETL is written against the standard library and boto3, and its contract is the schema file. Moving to Spark means rewriting `transform()` as DataFrame operations; the checks, the manifest, reconciliation and drift handling all stay the same.
- **EMR would only be justified** by an analytical workload this platform doesn't have, such as model training on years of servicing history.
