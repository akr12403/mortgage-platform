variable "environment" {
  description = "Environment name: dev, test or prod."
  type        = string
}

variable "iam_dir" {
  description = "Path to infrastructure/aws/iam (roles.json, trust/*.json, policies/*.json)."
  type        = string
}

variable "template_vars" {
  description = "Values for the $${VAR} placeholders in the IAM templates (resource names, prefixes, REGION, ACCOUNT_ID)."
  type        = map(string)
}

variable "developer_principal_arn" {
  description = "Role or user ARN trusted by trust/developer-assume.json (the developer session that assumes the app roles)."
  type        = string
}

variable "role_name_suffix" {
  description = "Appended to every M8 role name. Empty for dev (keeps the M8 names), -test / -prod otherwise."
  type        = string
  default     = ""
}

variable "ecs_task_role_names" {
  description = "M8 roles (manifest names) that ECS tasks may also assume."
  type        = list(string)
  default     = []
}

variable "ecr_repository_prefix" {
  description = "ECR repository namespace of this environment, e.g. capstone-mortgage-dev."
  type        = string
}

variable "ecs_log_group_prefix" {
  description = "CloudWatch log group prefix of this environment's ECS tasks, e.g. /ecs/capstone-mortgage-dev."
  type        = string
}

variable "ssm_parameter_path" {
  description = "SSM Parameter Store path holding this environment's secrets, e.g. /capstone-mortgage/dev."
  type        = string
}

variable "vpc_id" {
  description = "VPC of the ECS task security group."
  type        = string
}

variable "vpc_cidr_block" {
  description = "VPC CIDR (PostgreSQL egress is limited to it)."
  type        = string
}

variable "allowed_ingress_cidrs" {
  description = "CIDRs that may reach the service ports directly (demo only, e.g. your public IP /32). Empty = no inbound."
  type        = list(string)
  default     = []
  validation {
    condition     = !contains(var.allowed_ingress_cidrs, "0.0.0.0/0")
    error_message = "Opening the services to the whole internet (0.0.0.0/0) is not allowed; use your own IP /32."
  }
}

variable "service_ports" {
  description = "Container ports opened to allowed_ingress_cidrs."
  type        = list(number)
  default     = []
}
