output "lambda_function_arn" {
  description = "Document processor ARN."
  value       = aws_lambda_function.doc_processor.arn
}

output "glue_job_name" {
  description = "Glue ETL job name."
  value       = aws_glue_job.etl.name
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by service (the deploy job pushes here)."
  value       = { for k, r in aws_ecr_repository.service : k => r.repository_url }
}

output "ecs_service_names" {
  description = "ECS service names keyed by service."
  value       = { for k, s in aws_ecs_service.service : k => s.name }
}
