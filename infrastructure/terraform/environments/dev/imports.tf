# dev only: adopt the resources the M8 scripts created (scripts/aws/*-apply.sh / *-deploy.sh) instead of recreating
# them. `terraform plan` shows "N to import" plus small in-place updates (ManagedBy tag, ECS trust statement, Lambda
# zip hash); nothing is replaced. After the first successful apply these blocks are no-ops and may stay or be removed.
# In an empty account (M8 already torn down), delete this file and the plan simply creates everything.

locals {
  m8_roles   = ["mortgage-api-role", "mortgage-servicing-role", "mortgage-analytics-role", "lambda-doc-processor-role", "mortgage-glue-etl-role"]
  m8_buckets = { docs = local.names.DOCS_BUCKET, analytics = local.names.ANALYTICS_BUCKET }
  m8_tables  = { lookup = local.names.LOOKUP_TABLE, doc_metadata = local.names.DOC_METADATA_TABLE }
}

# ---------------------------------------------------------------- security (Task 8.1)
import {
  for_each = toset(local.m8_roles)
  to       = module.security.aws_iam_role.app[each.key]
  id       = each.key
}

import {
  for_each = toset(local.m8_roles)
  to       = module.security.aws_iam_role_policy.app[each.key]
  id       = "${each.key}:${each.key}-policy"
}

import {
  for_each = toset(local.m8_roles)
  to       = module.security.aws_iam_role_policies_exclusive.app[each.key]
  id       = each.key
}

import {
  for_each = toset(local.m8_roles)
  to       = module.security.aws_iam_role_policy_attachments_exclusive.app[each.key]
  id       = each.key
}

# ---------------------------------------------------------------- storage (Tasks 8.2, 8.3, 8.4)
import {
  for_each = local.m8_buckets
  to       = module.storage.aws_s3_bucket.this[each.key]
  id       = each.value
}

import {
  for_each = local.m8_buckets
  to       = module.storage.aws_s3_bucket_public_access_block.this[each.key]
  id       = each.value
}

import {
  for_each = local.m8_buckets
  to       = module.storage.aws_s3_bucket_ownership_controls.this[each.key]
  id       = each.value
}

import {
  for_each = local.m8_buckets
  to       = module.storage.aws_s3_bucket_server_side_encryption_configuration.this[each.key]
  id       = each.value
}

import {
  for_each = local.m8_buckets
  to       = module.storage.aws_s3_bucket_policy.this[each.key]
  id       = each.value
}

import {
  for_each = local.m8_buckets
  to       = module.storage.aws_s3_bucket_lifecycle_configuration.this[each.key]
  id       = each.value
}

import {
  for_each = local.m8_tables
  to       = module.storage.aws_dynamodb_table.this[each.key]
  id       = each.value
}

# ---------------------------------------------------------------- compute: document Lambda (Task 8.3)
import {
  to = module.compute.aws_cloudwatch_log_group.lambda
  id = "/aws/lambda/${local.names.LAMBDA_FUNCTION}"
}

import {
  to = module.compute.aws_lambda_function.doc_processor
  id = local.names.LAMBDA_FUNCTION
}

import {
  to = module.compute.aws_lambda_permission.s3_invoke
  id = "${local.names.LAMBDA_FUNCTION}/s3-docs-bucket-invoke"
}

import {
  to = module.compute.aws_s3_bucket_notification.docs
  id = local.names.DOCS_BUCKET
}

import {
  to = module.compute.aws_cloudwatch_metric_alarm.lambda_errors
  id = "${local.names.LAMBDA_FUNCTION}-errors"
}

# ---------------------------------------------------------------- compute: Glue job + failure alert (Tasks 8.5, 8.6)
import {
  to = module.compute.aws_s3_object.glue_script
  id = "${local.names.ANALYTICS_BUCKET}/${local.prefixes.GLUE_ASSETS_PREFIX}scripts/delinquency_report_etl.py"
}

import {
  to = module.compute.aws_s3_object.glue_schema
  id = "${local.names.ANALYTICS_BUCKET}/${local.prefixes.GLUE_ASSETS_PREFIX}schemas/delinquency_report.schema.json"
}

import {
  for_each = toset(["/aws-glue/python-jobs/output", "/aws-glue/python-jobs/error"])
  to       = module.compute.aws_cloudwatch_log_group.glue[each.key]
  id       = each.key
}

import {
  to = module.compute.aws_glue_job.etl
  id = local.names.GLUE_JOB
}

import {
  to = module.compute.aws_cloudwatch_log_group.pipeline_alerts
  id = local.names.PIPELINE_ALERT_LOG_GROUP
}

import {
  to = module.compute.aws_cloudwatch_log_resource_policy.pipeline_alerts
  id = "capstone-mortgage-pipeline-alerts"
}

import {
  to = module.compute.aws_cloudwatch_event_rule.glue_failed
  id = "${local.names.GLUE_JOB}-failed"
}

import {
  to = module.compute.aws_cloudwatch_event_target.glue_failed
  id = "${local.names.GLUE_JOB}-failed/pipeline-alert-log"
}
