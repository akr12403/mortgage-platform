#!/bin/bash
# Creates the M5 messaging topology in LocalStack (idempotent — safe to re-run):
#
#   SNS capstone-mortgage-lifecycle-dev
#     ├─> SQS capstone-mortgage-servicing-dev  (servicing-service) ──after 3 receives──> capstone-mortgage-servicing-dlq-dev
#     └─> SQS capstone-mortgage-analytics-dev  (analytics-service) ──after 3 receives──> capstone-mortgage-analytics-dlq-dev
#
# Queue settings: VisibilityTimeout=30s, maxReceiveCount=3, DLQ retention 14 days.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
VISIBILITY_TIMEOUT=30
MAX_RECEIVE_COUNT=3
TAGS='Project=mortgage-intelligence,Environment=dev,Team=capstone'

topic_arn=$(awslocal sns create-topic \
  --name capstone-mortgage-lifecycle-dev \
  --tags Key=Project,Value=mortgage-intelligence Key=Environment,Value=dev Key=Team,Value=capstone \
  --query TopicArn --output text)
echo "Topic: $topic_arn"

queue_arn() {
  awslocal sqs get-queue-attributes --queue-url "$1" --attribute-names QueueArn \
    --query 'Attributes.QueueArn' --output text
}

# create_consumer_queue <queue-name> <dlq-name>
create_consumer_queue() {
  local name="$1" dlq_name="$2"

  local dlq_url
  dlq_url=$(awslocal sqs create-queue --queue-name "$dlq_name" --query QueueUrl --output text)
  awslocal sqs set-queue-attributes --queue-url "$dlq_url" --attributes MessageRetentionPeriod=1209600
  awslocal sqs tag-queue --queue-url "$dlq_url" --tags "$TAGS"
  local dlq_arn
  dlq_arn=$(queue_arn "$dlq_url")

  local queue_url
  queue_url=$(awslocal sqs create-queue --queue-name "$name" --query QueueUrl --output text)
  awslocal sqs tag-queue --queue-url "$queue_url" --tags "$TAGS"

  local attributes
  attributes=$(python -c 'import json, sys; print(json.dumps({
      "VisibilityTimeout": sys.argv[2],
      "RedrivePolicy": json.dumps({"deadLetterTargetArn": sys.argv[1], "maxReceiveCount": sys.argv[3]})}))' \
    "$dlq_arn" "$VISIBILITY_TIMEOUT" "$MAX_RECEIVE_COUNT")
  awslocal sqs set-queue-attributes --queue-url "$queue_url" --attributes "$attributes"

  local q_arn
  q_arn=$(queue_arn "$queue_url")
  local existing
  existing=$(awslocal sns list-subscriptions-by-topic --topic-arn "$topic_arn" \
    --query "Subscriptions[?Endpoint=='$q_arn'].SubscriptionArn | [0]" --output text)
  if [[ -z "$existing" || "$existing" == "None" ]]; then
    awslocal sns subscribe --topic-arn "$topic_arn" --protocol sqs \
      --notification-endpoint "$q_arn" --attributes RawMessageDelivery=true >/dev/null
  fi
  echo "Queue: $queue_url -> DLQ: $dlq_url (VisibilityTimeout=${VISIBILITY_TIMEOUT}s, maxReceiveCount=${MAX_RECEIVE_COUNT})"
}

create_consumer_queue capstone-mortgage-servicing-dev capstone-mortgage-servicing-dlq-dev
create_consumer_queue capstone-mortgage-analytics-dev capstone-mortgage-analytics-dlq-dev

echo "Initialized mortgage lifecycle topic, consumer queues, DLQs and subscriptions in ${REGION}."
