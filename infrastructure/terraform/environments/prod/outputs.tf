output "vpc_id" {
  description = "VPC id."
  value       = module.networking.vpc_id
}

output "role_arns" {
  description = "M8 application role ARNs."
  value       = module.security.role_arns
}

output "bucket_names" {
  description = "S3 buckets."
  value       = module.storage.bucket_names
}

output "table_names" {
  description = "DynamoDB tables."
  value       = module.storage.table_names
}

output "lifecycle_topic_arn" {
  description = "SNS lifecycle topic."
  value       = module.messaging.topic_arn
}

output "queue_urls" {
  description = "SQS consumer queues."
  value       = module.messaging.queue_urls
}

output "ecr_repository_urls" {
  description = "ECR repositories (deploy target)."
  value       = module.compute.ecr_repository_urls
}

output "ecs_cluster_name" {
  description = "ECS cluster."
  value       = module.compute.ecs_cluster_name
}

output "ecs_service_names" {
  description = "ECS services."
  value       = module.compute.ecs_service_names
}
