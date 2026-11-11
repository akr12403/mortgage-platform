# Environment root (M9 Task 9.2). IDENTICAL in environments/dev, test and prod (checked by
# tests/infrastructure/test_terraform_layout.py): environments differ only in terraform.tfvars and backend.tf.
# Names follow guides/standards.md (capstone-mortgage-{resource}-{env}); for dev they equal the M8 names in
# infrastructure/aws/resources.conf, so the M8 resources are imported, not recreated (imports.tf, dev only).

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "mortgage-intelligence"
      Environment = var.environment
      Team        = "capstone"
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_iam_session_context" "current" {
  arn = data.aws_caller_identity.current.arn
}

locals {
  env      = var.environment
  aws_root = "${path.root}/../../../aws" # infrastructure/aws: M8 templates (single source of truth)

  names = {
    DOCS_BUCKET              = "capstone-mortgage-docs-${local.env}"
    ANALYTICS_BUCKET         = "capstone-mortgage-analytics-${local.env}"
    LIFECYCLE_TOPIC          = "capstone-mortgage-lifecycle-${local.env}"
    SERVICING_QUEUE          = "capstone-mortgage-servicing-${local.env}"
    ANALYTICS_QUEUE          = "capstone-mortgage-analytics-${local.env}"
    LOOKUP_TABLE             = "CapstoneMortgageLookup-${local.env}"
    DOC_METADATA_TABLE       = "CapstoneMortgageDocumentMetadata-${local.env}"
    LAMBDA_FUNCTION          = "capstone-mortgage-doc-processor-${local.env}"
    GLUE_JOB                 = "capstone-mortgage-delinquency-etl-${local.env}"
    PIPELINE_ALERT_LOG_GROUP = "/aws/events/capstone-mortgage-pipeline-alerts-${local.env}"
  }
  prefixes = {
    DOCS_UPLOAD_PREFIX = "mortgages/"
    RAW_PREFIX         = "raw/pg-export/"
    CURATED_PREFIX     = "curated/delinquency_report/"
    GLUE_ASSETS_PREFIX = "glue/"
  }
  template_vars = merge(local.names, local.prefixes, {
    REGION          = data.aws_region.current.region
    ACCOUNT_ID      = data.aws_caller_identity.current.account_id
    TAG_PROJECT     = "mortgage-intelligence"
    TAG_ENVIRONMENT = local.env
    TAG_TEAM        = "capstone"
  })

  # Who may assume the app roles for local runs (trust/developer-assume.json): the role behind the current session
  # unless set explicitly (CI sets it, so a pipeline role never becomes the trusted principal by accident).
  developer_principal_arn = coalesce(var.developer_principal_arn, data.aws_iam_session_context.current.issuer_arn)

  # M8 dev roles keep their original names; other environments get a suffix (same account, no collisions).
  role_suffix = local.env == "dev" ? "" : "-${local.env}"

  ecs_prefix = "capstone-mortgage-${local.env}"
  ssm_path   = "/capstone-mortgage/${local.env}"
}

module "networking" {
  source     = "../../modules/networking"
  name       = "capstone-mortgage-${local.env}"
  cidr_block = var.vpc_cidr
}

module "security" {
  source                  = "../../modules/security"
  environment             = local.env
  iam_dir                 = "${local.aws_root}/iam"
  template_vars           = local.template_vars
  developer_principal_arn = local.developer_principal_arn
  role_name_suffix        = local.role_suffix
  ecs_task_role_names     = ["mortgage-api-role", "mortgage-servicing-role", "mortgage-analytics-role"]
  ecr_repository_prefix   = local.ecs_prefix
  ecs_log_group_prefix    = "/ecs/${local.ecs_prefix}"
  ssm_parameter_path      = local.ssm_path
  vpc_id                  = module.networking.vpc_id
  vpc_cidr_block          = var.vpc_cidr
  allowed_ingress_cidrs   = var.allowed_ingress_cidrs
  service_ports           = local.service_ports
}

module "storage" {
  source        = "../../modules/storage"
  s3_dir        = "${local.aws_root}/s3"
  dynamodb_dir  = "${local.aws_root}/dynamodb"
  template_vars = local.template_vars
  force_destroy = var.sandbox_teardown
  buckets = {
    docs      = { name = local.names.DOCS_BUCKET, lifecycle_template = "lifecycle-docs.json" }
    analytics = { name = local.names.ANALYTICS_BUCKET, lifecycle_template = "lifecycle-analytics.json" }
  }
  tables = {
    lookup       = { template = "mortgage-lookup-table.json" }
    doc_metadata = { template = "document-metadata-table.json", ttl_attribute = "expiresAt" }
  }
}

module "messaging" {
  source     = "../../modules/messaging"
  topic_name = local.names.LIFECYCLE_TOPIC
  queues = {
    servicing = { name = local.names.SERVICING_QUEUE, dlq_name = "capstone-mortgage-servicing-dlq-${local.env}" }
    analytics = { name = local.names.ANALYTICS_QUEUE, dlq_name = "capstone-mortgage-analytics-dlq-${local.env}" }
  }
}

locals {
  # Fargate services. Plain settings here; secrets are SSM SecureString names under /capstone-mortgage/<env>/.
  # PostgreSQL is a placeholder (database_host): no RDS in Task 9.2 (handbook: "RDS or EC2/ECS placeholder").
  common_env = {
    AWS_REGION         = var.region
    LOG_LEVEL          = "INFO"
    POSTGRES_HOST      = var.database_host
    POSTGRES_PORT      = "5432"
    POSTGRES_DB        = "mortgage_intel"
    POSTGRES_USER      = "mortgage_app"
    JWT_ISSUER         = "capstone-mortgage-auth"
    RATE_LIMIT_ENABLED = "true"
  }
  service_ports = [8080, 8081, 8000, 8001] # must match the ports in local.services
  java_health   = ["CMD-SHELL", "curl -fsS http://localhost:%d/actuator/health || exit 1"]
  python_health = ["CMD", "python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:%d/health', timeout=3).status == 200 else 1)"]

  services = {
    mortgage-service = {
      port          = 8080
      cpu           = 512
      memory        = 1024
      health_check  = [for c in local.java_health : replace(c, "%d", "8080")]
      task_role_arn = module.security.role_arns["mortgage-api-role"]
      environment   = merge(local.common_env, { SPRING_PROFILES_ACTIVE = local.env, SNS_TOPIC_MORTGAGE_EVENTS = module.messaging.topic_arn })
      secrets       = ["JWT_SECRET", "POSTGRES_PASSWORD", "AUTH_SEED_PASSWORD"]
    }
    servicing-service = {
      port          = 8081
      cpu           = 512
      memory        = 1024
      health_check  = [for c in local.java_health : replace(c, "%d", "8081")]
      task_role_arn = module.security.role_arns["mortgage-servicing-role"]
      environment   = merge(local.common_env, { SPRING_PROFILES_ACTIVE = local.env, SQS_QUEUE_SERVICING_EVENTS = module.messaging.queue_urls["servicing"], SQS_MAX_RECEIVE_COUNT = "3" })
      secrets       = ["JWT_SECRET", "POSTGRES_PASSWORD"]
    }
    analytics-service = {
      port          = 8000
      cpu           = 256
      memory        = 512
      health_check  = [for c in local.python_health : replace(c, "%d", "8000")]
      task_role_arn = module.security.role_arns["mortgage-analytics-role"]
      environment   = merge(local.common_env, { SQS_QUEUE_ANALYTICS_EVENTS = module.messaging.queue_urls["analytics"], SQS_MAX_RECEIVE_COUNT = "3", S3_BUCKET_DOCUMENTS = local.names.DOCS_BUCKET })
      secrets       = ["JWT_SECRET", "POSTGRES_PASSWORD"]
    }
    knowledge-assistant = {
      port         = 8001
      cpu          = 256
      memory       = 512
      health_check = [for c in local.python_health : replace(c, "%d", "8001")]
      environment  = merge(local.common_env, { LLM_API_BASE = "https://api.openai.com/v1" })
      secrets      = ["JWT_SECRET", "POSTGRES_PASSWORD", "LLM_API_KEY"]
    }
  }
}

module "compute" {
  source     = "../../modules/compute"
  region     = var.region
  account_id = data.aws_caller_identity.current.account_id

  lambda_function_name = local.names.LAMBDA_FUNCTION
  lambda_role_arn      = module.security.role_arns["lambda-doc-processor-role"]
  lambda_source_dir    = "${local.aws_root}/lambda/doc_processor"
  docs_bucket          = module.storage.bucket_names["docs"]
  docs_upload_prefix   = local.prefixes.DOCS_UPLOAD_PREFIX
  doc_metadata_table   = module.storage.table_names["doc_metadata"]

  glue_job_name              = local.names.GLUE_JOB
  glue_role_arn              = module.security.role_arns["mortgage-glue-etl-role"]
  glue_dir                   = "${path.root}/../../../glue"
  analytics_bucket           = module.storage.bucket_names["analytics"]
  raw_prefix                 = local.prefixes.RAW_PREFIX
  curated_prefix             = local.prefixes.CURATED_PREFIX
  glue_assets_prefix         = local.prefixes.GLUE_ASSETS_PREFIX
  manage_glue_log_groups     = var.manage_account_wide_resources
  pipeline_alert_log_group   = local.names.PIPELINE_ALERT_LOG_GROUP
  pipeline_alert_policy_name = local.env == "dev" ? "capstone-mortgage-pipeline-alerts" : "capstone-mortgage-pipeline-alerts-${local.env}"

  services               = local.services
  image_tag              = var.image_tag
  desired_count          = var.desired_count
  ecs_cluster_name       = local.ecs_prefix
  ecr_repository_prefix  = local.ecs_prefix
  force_delete_images    = var.sandbox_teardown
  ecs_log_group_prefix   = "/ecs/${local.ecs_prefix}"
  ssm_parameter_path     = local.ssm_path
  ecs_execution_role_arn = module.security.ecs_execution_role_arn
  ecs_security_group_id  = module.security.ecs_tasks_security_group_id
  subnet_ids             = module.networking.public_subnet_ids
}
