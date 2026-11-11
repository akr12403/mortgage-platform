variable "region" {
  description = "AWS Region."
  type        = string
}

variable "account_id" {
  description = "AWS account id (from the caller identity at plan time, never committed)."
  type        = string
}

# ---------------------------------------------------------------- Lambda
variable "lambda_function_name" {
  description = "Document processor function name."
  type        = string
}

variable "lambda_role_arn" {
  description = "Execution role (lambda-doc-processor-role)."
  type        = string
}

variable "lambda_source_dir" {
  description = "Path to infrastructure/aws/lambda/doc_processor."
  type        = string
}

variable "docs_bucket" {
  description = "Documents bucket that triggers the Lambda."
  type        = string
}

variable "docs_upload_prefix" {
  description = "Key prefix of uploaded documents (trigger filter)."
  type        = string
}

variable "doc_metadata_table" {
  description = "DynamoDB table the Lambda writes."
  type        = string
}

# ---------------------------------------------------------------- Glue + alert
variable "glue_job_name" {
  description = "Glue ETL job name."
  type        = string
}

variable "glue_role_arn" {
  description = "Glue job role (mortgage-glue-etl-role)."
  type        = string
}

variable "glue_dir" {
  description = "Path to infrastructure/glue (job script and schemas)."
  type        = string
}

variable "analytics_bucket" {
  description = "Analytics bucket (raw, curated and glue/ prefixes)."
  type        = string
}

variable "raw_prefix" {
  description = "Raw export prefix."
  type        = string
}

variable "curated_prefix" {
  description = "Curated output prefix."
  type        = string
}

variable "glue_assets_prefix" {
  description = "Prefix of the job script and schema."
  type        = string
}

variable "manage_glue_log_groups" {
  description = "Manage the account-wide /aws-glue/python-jobs/* log groups (true in exactly one environment)."
  type        = bool
  default     = false
}

variable "pipeline_alert_log_group" {
  description = "Log group that receives failed Glue run events."
  type        = string
}

variable "pipeline_alert_policy_name" {
  description = "Name of the CloudWatch Logs resource policy for the alert log group (account-wide namespace)."
  type        = string
}

# ---------------------------------------------------------------- ECS
variable "services" {
  description = "Fargate services keyed by name: port, size, container health check, task role, plain env, SSM secret names."
  type = map(object({
    port          = number
    cpu           = number
    memory        = number
    health_check  = list(string)
    task_role_arn = optional(string)
    environment   = optional(map(string), {})
    secrets       = optional(list(string), [])
  }))
}

variable "image_tag" {
  description = "Immutable image tag deployed to every service (sha-<commit> or a semver). Set by the deploy job."
  type        = string
}

variable "desired_count" {
  description = "Tasks per service. 0 = idle (no Fargate cost); 1 for a demo."
  type        = number
  default     = 0
}

variable "ecs_cluster_name" {
  description = "ECS cluster name; also the task definition family prefix."
  type        = string
}

variable "ecr_repository_prefix" {
  description = "ECR namespace, e.g. capstone-mortgage-dev (repositories <prefix>/<service>)."
  type        = string
}

variable "ecr_keep_images" {
  description = "Images kept per repository (older ones expire)."
  type        = number
  default     = 10
}

variable "force_delete_images" {
  description = "Let terraform destroy delete repositories that still hold images (sandbox teardown)."
  type        = bool
  default     = false
}

variable "ecs_log_group_prefix" {
  description = "Log group prefix of the services, e.g. /ecs/capstone-mortgage-dev."
  type        = string
}

variable "ssm_parameter_path" {
  description = "SSM path of the service secrets, e.g. /capstone-mortgage/dev."
  type        = string
}

variable "ecs_execution_role_arn" {
  description = "ECS task execution role."
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group of the tasks."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets of the tasks."
  type        = list(string)
}
