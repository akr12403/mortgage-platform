#!/bin/bash
set -euo pipefail

topic_arn=$(awslocal sns create-topic \
  --name capstone-mortgage-lifecycle-dev \
  --query TopicArn \
  --output text)

dlq_url=$(awslocal sqs create-queue \
  --queue-name capstone-mortgage-servicing-dlq-dev \
  --query QueueUrl \
  --output text)
dlq_arn=$(awslocal sqs get-queue-attributes \
  --queue-url "$dlq_url" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

queue_url=$(awslocal sqs create-queue \
  --queue-name capstone-mortgage-servicing-dev \
  --attributes "{\"VisibilityTimeout\":\"30\"}" \
  --query QueueUrl \
  --output text)
redrive_attributes=$(python -c 'import json, sys; print(json.dumps({"RedrivePolicy": json.dumps({"deadLetterTargetArn": sys.argv[1], "maxReceiveCount": "3"})}))' "$dlq_arn")
awslocal sqs set-queue-attributes \
  --queue-url "$queue_url" \
  --attributes "$redrive_attributes"
queue_arn=$(awslocal sqs get-queue-attributes \
  --queue-url "$queue_url" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

subscription_arn=$(awslocal sns list-subscriptions-by-topic \
  --topic-arn "$topic_arn" \
  --query "Subscriptions[?Endpoint=='$queue_arn'].SubscriptionArn | [0]" \
  --output text)

if [[ -z "$subscription_arn" || "$subscription_arn" == "None" ]]; then
  awslocal sns subscribe \
    --topic-arn "$topic_arn" \
    --protocol sqs \
    --notification-endpoint "$queue_arn" \
    --attributes RawMessageDelivery=true >/dev/null
fi

echo "Initialized mortgage lifecycle topic and servicing queue with DLQ."