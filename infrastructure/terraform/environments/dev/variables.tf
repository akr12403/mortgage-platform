variable "environment" {
  description = "Environment name; used in every resource name and the Environment tag."
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod."
  }
}

variable "region" {
  description = "AWS Region. The sandbox project is pinned to us-east-2 (SCP RegionFloor)."
  type        = string
  default     = "us-east-2"
}

variable "vpc_cidr" {
  description = "VPC CIDR of this environment."
  type        = string
}

variable "allowed_ingress_cidrs" {
  description = "Your public IP as x.x.x.x/32 to reach the services during a demo (pass with -var, do not commit). Empty = no inbound."
  type        = list(string)
  default     = []
}

variable "developer_principal_arn" {
  description = "Principal trusted to assume the app roles for local runs. Null = the role behind the current session."
  type        = string
  default     = null
}

variable "image_tag" {
  description = "Immutable image tag for all four services (sha-<commit> or semver)."
  type        = string
  default     = "unset"
}

variable "desired_count" {
  description = "Tasks per ECS service: 0 idle (default), 1 for a demo."
  type        = number
  default     = 0
}

variable "database_host" {
  description = "PostgreSQL host for the services (placeholder: no database is provisioned in Task 9.2)."
  type        = string
  default     = ""
}

variable "sandbox_teardown" {
  description = "Allow terraform destroy to delete non-empty buckets and ECR repositories. Never true for prod."
  type        = bool
  default     = false
}

variable "manage_account_wide_resources" {
  description = "Manage resources shared by all environments of the account (Glue python-jobs log groups). True in dev only."
  type        = bool
  default     = false
}
