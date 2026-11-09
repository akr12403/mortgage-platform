# messaging: the M5 event topology on real SNS/SQS (same shape as localstack/init/ready.d/01-create-mortgage-messaging.sh)
#
#   SNS <topic>
#     ├─> SQS <consumer queue>  ──after max_receive_count receives──> <consumer>-dlq
#     └─> ...
# Raw message delivery, visibility timeout 30 s, DLQ retention 14 days, SQS-managed encryption at rest.
# Kinesis is not used (ADR-003; not available on the sandbox's Free plan).

resource "aws_sns_topic" "lifecycle" {
  name = var.topic_name
}

resource "aws_sqs_queue" "dlq" {
  for_each                  = var.queues
  name                      = each.value.dlq_name
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "consumer" {
  for_each                   = var.queues
  name                       = each.value.name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Only the lifecycle topic may send to the consumer queues.
resource "aws_sqs_queue_policy" "consumer" {
  for_each  = var.queues
  queue_url = aws_sqs_queue.consumer[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LifecycleTopicDeliversHere"
      Effect    = "Allow"
      Principal = { Service = "sns.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.consumer[each.key].arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.lifecycle.arn } }
    }]
  })
}

resource "aws_sns_topic_subscription" "consumer" {
  for_each             = var.queues
  topic_arn            = aws_sns_topic.lifecycle.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.consumer[each.key].arn
  raw_message_delivery = true
  depends_on           = [aws_sqs_queue_policy.consumer]
}
