variable "name" {
  description = "Name prefix for the networking resources, e.g. capstone-mortgage-dev."
  type        = string
}

variable "cidr_block" {
  description = "VPC CIDR. Each environment uses its own range so they could be peered later."
  type        = string
}

variable "az_count" {
  description = "Number of Availability Zones (one public subnet each)."
  type        = number
  default     = 2
  validation {
    condition     = var.az_count >= 1 && var.az_count <= 3
    error_message = "az_count must be between 1 and 3."
  }
}
