variable "topic_name" {
  description = "SNS topic for mortgage lifecycle events."
  type        = string
}

variable "queues" {
  description = "Consumer queues keyed by consumer (servicing, analytics): queue name and DLQ name."
  type = map(object({
    name     = string
    dlq_name = string
  }))
}

variable "visibility_timeout_seconds" {
  description = "Consumer queue visibility timeout."
  type        = number
  default     = 30
}

variable "max_receive_count" {
  description = "Receives before a message moves to the DLQ."
  type        = number
  default     = 3
}
