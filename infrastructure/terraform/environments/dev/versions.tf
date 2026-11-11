terraform {
  # 1.10+: S3 backend native locking (use_lockfile). 1.7+: import blocks with for_each.
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.40"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}
