variable "s3_dir" {
  description = "Path to infrastructure/aws/s3 (bucket-policy.json, lifecycle-*.json)."
  type        = string
}

variable "dynamodb_dir" {
  description = "Path to infrastructure/aws/dynamodb (table definitions)."
  type        = string
}

variable "template_vars" {
  description = "Values for the $${VAR} placeholders in the templates."
  type        = map(string)
}

variable "buckets" {
  description = "Buckets keyed by role (docs, analytics): name and lifecycle template file."
  type = map(object({
    name               = string
    lifecycle_template = string
  }))
}

variable "tables" {
  description = "DynamoDB tables keyed by role: template file and optional TTL attribute."
  type = map(object({
    template      = string
    ttl_attribute = optional(string)
  }))
}

variable "force_destroy" {
  description = "Let terraform destroy delete non-empty buckets (sandbox teardown). Keep false for prod."
  type        = bool
  default     = false
}
