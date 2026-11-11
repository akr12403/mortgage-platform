# ECS Fargate platform for the four services (M9 decision: ECS Fargate, on demand).
# Images: CI copies the tested, scanned GHCR image (sha-<commit>) into this environment's ECR repository (Task 9.1
# part B); task definitions always reference an immutable tag. Services default to desired_count = 0: the cluster,
# task definitions and repositories cost nothing while idle; scale up for a demo, back to 0 afterwards.
# No load balancer (~$16/month): tasks get a public IP and the security group admits only allowed_ingress_cidrs.

resource "aws_ecr_repository" "service" {
  for_each             = var.services
  name                 = "${var.ecr_repository_prefix}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.force_delete_images
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = var.services
  repository = aws_ecr_repository.service[each.key].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last ${var.ecr_keep_images} images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = var.ecr_keep_images }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "this" {
  name = var.ecs_cluster_name
  setting {
    name  = "containerInsights"
    value = "disabled" # cost: enable for load tests / Task 9.3 if CloudWatch metrics are needed
  }
}

resource "aws_cloudwatch_log_group" "service" {
  for_each          = var.services
  name              = "${var.ecs_log_group_prefix}/${each.key}"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "service" {
  for_each                 = var.services
  family                   = "${var.ecs_cluster_name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = each.value.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64" # CI builds linux/amd64 images on ubuntu-latest
  }

  container_definitions = jsonencode([{
    name         = each.key
    image        = "${aws_ecr_repository.service[each.key].repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = each.value.port, protocol = "tcp" }]
    environment  = [for k, v in each.value.environment : { name = k, value = v }]
    # Secrets are SSM SecureString parameters created outside Terraform (values never enter state or Git).
    secrets = [for s in each.value.secrets : {
      name      = s
      valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter${var.ssm_parameter_path}/${s}"
    }]
    healthCheck = { command = each.value.health_check, interval = 15, timeout = 5, retries = 5, startPeriod = 60 }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.service[each.key].name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = each.key
      }
    }
  }])
}

resource "aws_ecs_service" "service" {
  for_each               = var.services
  name                   = each.key
  cluster                = aws_ecs_cluster.this.id
  task_definition        = aws_ecs_task_definition.service[each.key].arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true # no NAT gateway: needed to pull from ECR and reach AWS APIs
  }

  # A deployment whose tasks never become healthy is stopped and rolled back to the last working task definition.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
}
