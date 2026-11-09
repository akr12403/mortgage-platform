output "topic_arn" {
  description = "Lifecycle topic ARN (SNS_TOPIC_MORTGAGE_EVENTS)."
  value       = aws_sns_topic.lifecycle.arn
}

output "queue_urls" {
  description = "Consumer queue URLs keyed by consumer (SQS_QUEUE_*_EVENTS)."
  value       = { for k, q in aws_sqs_queue.consumer : k => q.url }
}

output "dlq_urls" {
  description = "DLQ URLs keyed by consumer."
  value       = { for k, q in aws_sqs_queue.dlq : k => q.url }
}
