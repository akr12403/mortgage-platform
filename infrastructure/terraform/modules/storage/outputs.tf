output "bucket_names" {
  description = "Bucket names keyed by role."
  value       = { for k, b in aws_s3_bucket.this : k => b.bucket }
}

output "bucket_arns" {
  description = "Bucket ARNs keyed by role."
  value       = { for k, b in aws_s3_bucket.this : k => b.arn }
}

output "table_names" {
  description = "DynamoDB table names keyed by role."
  value       = { for k, t in aws_dynamodb_table.this : k => t.name }
}
