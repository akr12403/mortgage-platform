# compute: the M8 serverless pieces and the M9 container platform.
#   main.tf  document Lambda (Task 8.3) + Glue ETL job and its failure alert (Tasks 8.5, 8.6)
#   ecs.tf   ECR repositories, ECS cluster, Fargate task definitions and services (desired_count 0 until a demo)

# ---------------------------------------------------------------- Document processor Lambda (Task 8.3)
data "archive_file" "doc_processor" {
  type             = "zip"
  source_file      = "${var.lambda_source_dir}/handler.py"
  output_path      = "${path.root}/.build/doc-processor.zip"
  output_file_mode = "0644"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "doc_processor" {
  function_name    = var.lambda_function_name
  description      = "M8: validate uploaded mortgage documents, write metadata to DynamoDB"
  role             = var.lambda_role_arn
  runtime          = "python3.14"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  timeout          = 30
  memory_size      = 256
  filename         = data.archive_file.doc_processor.output_path
  source_code_hash = data.archive_file.doc_processor.output_base64sha256

  environment {
    variables = {
      DOC_METADATA_TABLE      = var.doc_metadata_table
      DOCS_UPLOAD_PREFIX      = var.docs_upload_prefix
      MAX_DOCUMENT_BYTES      = "10485760"
      METADATA_RETENTION_DAYS = "30"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }
}

resource "aws_lambda_permission" "s3_invoke" {
  statement_id   = "s3-docs-bucket-invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.doc_processor.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = "arn:aws:s3:::${var.docs_bucket}"
  source_account = var.account_id
}

resource "aws_s3_bucket_notification" "docs" {
  bucket = var.docs_bucket
  lambda_function {
    id                  = "doc-processor-on-upload"
    lambda_function_arn = aws_lambda_function.doc_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.docs_upload_prefix
  }
  depends_on = [aws_lambda_permission.s3_invoke]
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.lambda_function_name}-errors"
  alarm_description   = "M8 stub: document Lambda failed at least once in 5 minutes. No action attached; runbook: docs/architecture/aws-document-lambda.md#error-alarm"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.doc_processor.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

# ---------------------------------------------------------------- Glue ETL job (Task 8.5)
locals {
  glue_script_key = "${var.glue_assets_prefix}scripts/delinquency_report_etl.py"
  glue_schema_key = "${var.glue_assets_prefix}schemas/delinquency_report.schema.json"
}

resource "aws_s3_object" "glue_script" {
  bucket       = var.analytics_bucket
  key          = local.glue_script_key
  source       = "${var.glue_dir}/delinquency_report_etl.py"
  etag         = filemd5("${var.glue_dir}/delinquency_report_etl.py")
  content_type = "text/x-python"
}

resource "aws_s3_object" "glue_schema" {
  bucket       = var.analytics_bucket
  key          = local.glue_schema_key
  source       = "${var.glue_dir}/schemas/delinquency_report.schema.json"
  etag         = filemd5("${var.glue_dir}/schemas/delinquency_report.schema.json")
  content_type = "application/json"
}

# Python shell jobs write to these account-wide groups; only one environment (dev) manages them.
resource "aws_cloudwatch_log_group" "glue" {
  for_each          = var.manage_glue_log_groups ? toset(["/aws-glue/python-jobs/output", "/aws-glue/python-jobs/error"]) : toset([])
  name              = each.value
  retention_in_days = 7
}

resource "aws_glue_job" "etl" {
  name         = var.glue_job_name
  description  = "M8: PostgreSQL export (raw) -> delinquency_report (curated), schema-checked"
  role_arn     = var.glue_role_arn
  max_capacity = 0.0625
  timeout      = 10
  max_retries  = 0
  command {
    name            = "pythonshell"
    python_version  = "3.9"
    script_location = "s3://${var.analytics_bucket}/${aws_s3_object.glue_script.key}"
  }
  execution_property {
    max_concurrent_runs = 1
  }
  default_arguments = {
    "--library-set"         = "analytics"
    "--BUCKET"              = var.analytics_bucket
    "--RAW_PREFIX"          = var.raw_prefix
    "--CURATED_PREFIX"      = var.curated_prefix
    "--SCHEMA_KEY"          = aws_s3_object.glue_schema.key
    "--SCHEMA_DRIFT_MODE"   = "fail"
    "--enable-job-insights" = "false"
  }
}

# ---------------------------------------------------------------- Failed-run alert (Task 8.6)
resource "aws_cloudwatch_log_group" "pipeline_alerts" {
  name              = var.pipeline_alert_log_group
  retention_in_days = 30
}

# Only EventBridge may write, and only to this one log group.
resource "aws_cloudwatch_log_resource_policy" "pipeline_alerts" {
  policy_name = var.pipeline_alert_policy_name
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EventBridgeWritesPipelineAlerts"
      Effect    = "Allow"
      Principal = { Service = ["events.amazonaws.com", "delivery.logs.amazonaws.com"] }
      Action    = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource  = "${aws_cloudwatch_log_group.pipeline_alerts.arn}:*"
    }]
  })
}

resource "aws_cloudwatch_event_rule" "glue_failed" {
  name        = "${var.glue_job_name}-failed"
  description = "M8 Task 8.6: alert on failed runs of ${var.glue_job_name} (stub sink: CloudWatch Logs)"
  state       = "ENABLED"
  event_pattern = jsonencode({
    source        = ["aws.glue"]
    "detail-type" = ["Glue Job State Change"]
    detail = {
      jobName = [var.glue_job_name]
      state   = ["FAILED", "TIMEOUT", "ERROR", "STOPPED"]
    }
  })
}

resource "aws_cloudwatch_event_target" "glue_failed" {
  rule      = aws_cloudwatch_event_rule.glue_failed.name
  target_id = "pipeline-alert-log"
  arn       = aws_cloudwatch_log_group.pipeline_alerts.arn
}
