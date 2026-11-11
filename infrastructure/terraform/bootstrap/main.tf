# bootstrap: the S3 bucket that holds every environment's remote state (run once per account, before any env).
#   bash scripts/terraform/tf.sh bootstrap init
#   bash scripts/terraform/tf.sh bootstrap apply
# Chicken-and-egg: this configuration keeps its own (tiny) state locally in bootstrap/terraform.tfstate, which is
# git-ignored. Losing it is harmless: `terraform import aws_s3_bucket.state capstone-mortgage-tfstate-<account>`.
# Name: capstone-mortgage-tfstate-<account id> (globally unique, and the account id is never committed).

terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.40"
    }
  }
}

variable "region" {
  description = "AWS Region of the state bucket."
  type        = string
  default     = "us-east-2"
}

variable "force_destroy_state" {
  description = "Final cleanup only: let terraform destroy delete the state bucket with all its object versions."
  type        = bool
  default     = false
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "mortgage-intelligence"
      Environment = "shared"
      Team        = "capstone"
      ManagedBy   = "terraform-bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "state" {
  bucket        = "capstone-mortgage-tfstate-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.force_destroy_state # false: the state of every environment is never deleted by accident
}

# Versioning: every state write is kept, so a bad apply or a corrupted state can be rolled back.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# Old state versions are kept 30 days (rollback window), then expire; no Glacier (denied by the sandbox SCP).
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-noncurrent-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
  depends_on = [aws_s3_bucket_versioning.state]
}

output "state_bucket" {
  description = "Pass to the environments as -backend-config=bucket=<this> (scripts/terraform/tf.sh does it)."
  value       = aws_s3_bucket.state.bucket
}
