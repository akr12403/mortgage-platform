# security: the M8 least-privilege IAM roles, the ECS task execution role and the ECS task security group.
#
# Single source of truth: roles, trust policies and permission policies are read from infrastructure/aws/iam/
# (roles.json + templates), the same files the M8 scripts, the IAM policy simulator checks and
# tests/security/test_iam_policies.py use. Terraform renders them with templatefile(); it does not redefine them.
# Every role keeps exactly one inline policy and no managed policies (enforced by the *_exclusive resources).

locals {
  manifest = { for r in jsondecode(file("${var.iam_dir}/roles.json")).roles : r.name => r }
  vars     = merge(var.template_vars, { DEV_PRINCIPAL_ARN = var.developer_principal_arn })

  # Render a template, then drop documentation keys such as "_comment" (same as scripts/aws/lib.sh render()).
  trust = {
    for name, r in local.manifest : name => {
      for k, v in jsondecode(templatefile("${var.iam_dir}/${r.trust}", local.vars)) : k => v if !startswith(k, "_")
    }
  }
  policy = {
    for name, r in local.manifest : name => {
      for k, v in jsondecode(templatefile("${var.iam_dir}/${r.policy}", local.vars)) : k => v if !startswith(k, "_")
    }
  }

  # M9: the application roles may also be assumed by ECS tasks of THIS account (Fargate services, modules/compute).
  ecs_trust_statement = {
    Sid       = "EcsTasksOfThisAccountAssumeForFargateServices"
    Effect    = "Allow"
    Principal = { Service = "ecs-tasks.amazonaws.com" }
    Action    = "sts:AssumeRole"
    Condition = {
      StringEquals = { "aws:SourceAccount" = var.template_vars.ACCOUNT_ID }
      ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:${var.template_vars.REGION}:${var.template_vars.ACCOUNT_ID}:*" }
    }
  }
  # Encoded to JSON in both branches: the two documents have different shapes (1 vs 2 statements), which a
  # conditional can't return as objects.
  trust_json = {
    for name, doc in local.trust : name => (
      contains(var.ecs_task_role_names, name)
      ? jsonencode(merge(doc, { Statement = concat(doc.Statement, [local.ecs_trust_statement]) }))
      : jsonencode(doc)
    )
  }
}

resource "aws_iam_role" "app" {
  for_each             = local.manifest
  name                 = "${each.key}${var.role_name_suffix}"
  description          = each.value.description
  assume_role_policy   = local.trust_json[each.key]
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "app" {
  for_each = local.manifest
  name     = "${each.key}${var.role_name_suffix}-policy"
  role     = aws_iam_role.app[each.key].id
  policy   = jsonencode(local.policy[each.key])
}

# Exactly the one inline policy above, and no managed policies: anything added in the console shows up as drift.
resource "aws_iam_role_policies_exclusive" "app" {
  for_each     = local.manifest
  role_name    = aws_iam_role.app[each.key].name
  policy_names = [aws_iam_role_policy.app[each.key].name]
}

resource "aws_iam_role_policy_attachments_exclusive" "app" {
  for_each    = local.manifest
  role_name   = aws_iam_role.app[each.key].name
  policy_arns = []
}

# ---------------------------------------------------------------- ECS task execution role (pull image, logs, secrets)
# Used by the ECS agent, not by the application. Inline least-privilege policy instead of the broad AWS managed
# AmazonECSTaskExecutionRolePolicy: only this environment's ECR repositories, log groups and SSM parameters.
resource "aws_iam_role" "ecs_execution" {
  name                 = "capstone-mortgage-ecs-execution-${var.environment}"
  description          = "ECS agent: pull this environment's images, write its task logs, read its SSM secrets."
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EcsTasksAssumeExecutionRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = var.template_vars.ACCOUNT_ID } }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_execution" {
  name = "capstone-mortgage-ecs-execution-${var.environment}-policy"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuthTokenIsAccountWide"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid      = "PullThisEnvironmentsImages"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = "arn:aws:ecr:${var.template_vars.REGION}:${var.template_vars.ACCOUNT_ID}:repository/${var.ecr_repository_prefix}/*"
      },
      {
        Sid      = "WriteThisEnvironmentsTaskLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.template_vars.REGION}:${var.template_vars.ACCOUNT_ID}:log-group:${var.ecs_log_group_prefix}/*:*"
      },
      {
        Sid      = "ReadThisEnvironmentsSecrets"
        Effect   = "Allow"
        Action   = "ssm:GetParameters"
        Resource = "arn:aws:ssm:${var.template_vars.REGION}:${var.template_vars.ACCOUNT_ID}:parameter${var.ssm_parameter_path}/*"
      },
    ]
  })
}

resource "aws_iam_role_policies_exclusive" "ecs_execution" {
  role_name    = aws_iam_role.ecs_execution.name
  policy_names = [aws_iam_role_policy.ecs_execution.name]
}

# ---------------------------------------------------------------- ECS task security group
resource "aws_security_group" "ecs_tasks" {
  name        = "capstone-mortgage-ecs-tasks-${var.environment}"
  description = "Fargate tasks: inbound only from allowed_ingress_cidrs on the service ports; outbound HTTPS/DB."
  vpc_id      = var.vpc_id
  tags        = { Name = "capstone-mortgage-ecs-tasks-${var.environment}" }
}

resource "aws_vpc_security_group_ingress_rule" "service_ports" {
  for_each          = { for pair in setproduct(var.allowed_ingress_cidrs, var.service_ports) : "${pair[0]}:${pair[1]}" => pair }
  security_group_id = aws_security_group.ecs_tasks.id
  description       = "Service port ${each.value[1]} from ${each.value[0]} (demo access, no load balancer)"
  cidr_ipv4         = each.value[0]
  ip_protocol       = "tcp"
  from_port         = each.value[1]
  to_port           = each.value[1]
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.ecs_tasks.id
  description       = "HTTPS to ECR, CloudWatch Logs, SSM, SNS/SQS/S3/DynamoDB and the LLM API"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "postgres" {
  security_group_id = aws_security_group.ecs_tasks.id
  description       = "PostgreSQL inside the VPC (placeholder until a database is provisioned)"
  cidr_ipv4         = var.vpc_cidr_block
  ip_protocol       = "tcp"
  from_port         = 5432
  to_port           = 5432
}
