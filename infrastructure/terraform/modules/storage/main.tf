# storage: the S3 buckets (M8 Task 8.2) and DynamoDB tables (Tasks 8.3, 8.4).
# Bucket policy, lifecycle rules and table definitions are rendered from infrastructure/aws/{s3,dynamodb}/*.json,
# the same templates the M8 scripts used, so the hardening is defined once.

locals {
  lifecycle = {
    for key, b in var.buckets : key => jsondecode(templatefile("${var.s3_dir}/${b.lifecycle_template}", var.template_vars)).Rules
  }
  tables = {
    for key, t in var.tables : key => jsondecode(templatefile("${var.dynamodb_dir}/${t.template}", var.template_vars))
  }
}

resource "aws_s3_bucket" "this" {
  for_each      = var.buckets
  bucket        = each.value.name
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = var.buckets
  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    object_ownership = "BucketOwnerEnforced" # ACLs disabled
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each   = var.buckets
  bucket     = aws_s3_bucket.this[each.key].id
  policy     = jsonencode(jsondecode(templatefile("${var.s3_dir}/bucket-policy.json", merge(var.template_vars, { BUCKET = each.value.name }))))
  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id

  dynamic "rule" {
    for_each = local.lifecycle[each.key]
    content {
      id     = rule.value.ID
      status = rule.value.Status
      filter {
        prefix = try(rule.value.Filter.Prefix, null)
      }
      dynamic "expiration" {
        for_each = can(rule.value.Expiration.Days) ? [rule.value.Expiration.Days] : []
        content {
          days = expiration.value
        }
      }
      dynamic "abort_incomplete_multipart_upload" {
        for_each = can(rule.value.AbortIncompleteMultipartUpload.DaysAfterInitiation) ? [rule.value.AbortIncompleteMultipartUpload.DaysAfterInitiation] : []
        content {
          days_after_initiation = abort_incomplete_multipart_upload.value
        }
      }
    }
  }
}

resource "aws_dynamodb_table" "this" {
  for_each     = var.tables
  name         = local.tables[each.key].TableName
  billing_mode = local.tables[each.key].BillingMode
  hash_key     = one([for k in local.tables[each.key].KeySchema : k.AttributeName if k.KeyType == "HASH"])
  range_key    = one([for k in local.tables[each.key].KeySchema : k.AttributeName if k.KeyType == "RANGE"])

  dynamic "attribute" {
    for_each = local.tables[each.key].AttributeDefinitions
    content {
      name = attribute.value.AttributeName
      type = attribute.value.AttributeType
    }
  }

  dynamic "ttl" {
    for_each = each.value.ttl_attribute == null ? [] : [each.value.ttl_attribute]
    content {
      enabled        = true
      attribute_name = ttl.value
    }
  }
  # SSESpecification Enabled=false in the template = DynamoDB's default AWS-owned key (no server_side_encryption block).
}
