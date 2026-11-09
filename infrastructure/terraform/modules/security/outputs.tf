output "role_arns" {
  description = "ARNs of the M8 roles, keyed by manifest name (e.g. mortgage-api-role)."
  value       = { for k, r in aws_iam_role.app : k => r.arn }
}

output "ecs_execution_role_arn" {
  description = "ECS task execution role ARN."
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_tasks_security_group_id" {
  description = "Security group of the Fargate tasks."
  value       = aws_security_group.ecs_tasks.id
}
