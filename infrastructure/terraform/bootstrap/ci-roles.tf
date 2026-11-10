# CI access to AWS without access keys (M9 Task 9.1 part B, backlog B-20): GitHub Actions OIDC -> short-lived roles.
#
#   capstone-mortgage-ci-plan        PRs, develop, main, the nightly drift check: read-only + the state lock.
#   capstone-mortgage-ci-deploy-dev  pushes to develop and manual runs on develop only: plan + apply dev,
#                                    push images to dev's ECR. Writes are scoped to dev's named resources.
#
# SANDBOX STATUS: switched off (enable_github_oidc = false). The sandbox organization's SCP denies
# iam:CreateOpenIDConnectProvider (explicit deny, verified 2026-11-09), so GitHub cannot be trusted as an identity
# provider in this account and CI has no AWS access (no access keys by policy). Deploys run with the developer
# session instead: scripts/deploy/deploy-dev.sh (the same steps as the CI job). To switch CI on in an account that
# allows it: set enable_github_oidc = true, apply bootstrap, add the 3 repository secrets, set the repository
# variable AWS_OIDC_ENABLED = true. No workflow change is needed.
#
# Both: 1-hour sessions, trust limited to this repository (and the branch for deploy), and an explicit deny on
# business-data reads (DynamoDB items, SQS messages, documents and exports in S3, SSM/Secrets Manager values,
# log contents): Terraform only needs configuration. Managed outside CI: these roles, the state bucket, and
# break-glass changes (developer session, docs/operations/runbook.md).

variable "enable_github_oidc" {
  description = "Create the GitHub OIDC provider and the CI roles. False in the sandbox: its SCP denies iam:CreateOpenIDConnectProvider."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "owner/repo whose workflows may assume the CI roles."
  type        = string
  default     = "akr12403/mortgage-platform"
}

data "aws_iam_session_context" "current" {
  arn = data.aws_caller_identity.current.arn
}

locals {
  account = data.aws_caller_identity.current.account_id
  region  = var.region
  arn     = "arn:aws"

  # Roles the dev environment manages (M8 roles keep their names in dev; see environments/*/main.tf).
  dev_role_names = [
    "mortgage-api-role", "mortgage-servicing-role", "mortgage-analytics-role",
    "lambda-doc-processor-role", "mortgage-glue-etl-role", "capstone-mortgage-ecs-execution-dev",
  ]

  github_oidc_audience = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }

  deny_business_data_reads = [
    {
      Sid    = "NoBusinessDataReads"
      Effect = "Deny"
      Action = [
        "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:PartiQLSelect",
        "sqs:ReceiveMessage", "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath",
        "secretsmanager:GetSecretValue", "logs:GetLogEvents", "logs:FilterLogEvents", "logs:StartQuery",
      ]
      Resource = "*"
    },
    {
      Sid    = "NoDocumentOrExportReads"
      Effect = "Deny"
      Action = ["s3:GetObject", "s3:GetObjectVersion"]
      Resource = [
        "${local.arn}:s3:::capstone-mortgage-docs-*/*",
        "${local.arn}:s3:::capstone-mortgage-analytics-*/raw/*",
        "${local.arn}:s3:::capstone-mortgage-analytics-*/curated/*",
      ]
    },
  ]
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.enable_github_oidc ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# ---------------------------------------------------------------- plan role (read-only)
resource "aws_iam_role" "ci_plan" {
  count                = var.enable_github_oidc ? 1 : 0
  name                 = "capstone-mortgage-ci-plan"
  description          = "GitHub Actions: terraform plan for dev/test/prod and drift checks. Read-only plus the state lock."
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "GithubActionsOfThisRepository"
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github[0].arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = local.github_oidc_audience
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_repository}:pull_request",
            "repo:${var.github_repository}:ref:refs/heads/develop",
            "repo:${var.github_repository}:ref:refs/heads/main",
          ]
        }
      }
    }]
  })
}

# AWS managed ReadOnlyAccess: Terraform refreshes ~90 resources across 12 services; listing every Describe/Get/List
# action would be brittle. The explicit denies below remove the data-plane reads it includes.
resource "aws_iam_role_policy_attachment" "ci_plan_readonly" {
  count      = var.enable_github_oidc ? 1 : 0
  role       = aws_iam_role.ci_plan[0].name
  policy_arn = "${local.arn}:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "ci_plan" {
  count = var.enable_github_oidc ? 1 : 0
  name  = "capstone-mortgage-ci-plan-policy"
  role  = aws_iam_role.ci_plan[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid      = "ReadEveryEnvironmentsState"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.state.arn}/mortgage-platform/*"
      },
      {
        Sid      = "TakeAndReleaseTheStateLockOnly"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.state.arn}/mortgage-platform/*.tflock"
      },
      {
        Sid      = "ListTheStateBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.state.arn
      },
    ], local.deny_business_data_reads)
  })
}

# ---------------------------------------------------------------- deploy role (dev only)
resource "aws_iam_role" "ci_deploy_dev" {
  count                = var.enable_github_oidc ? 1 : 0
  name                 = "capstone-mortgage-ci-deploy-dev"
  description          = "GitHub Actions on develop: terraform apply for dev and image pushes to dev ECR. Dev resources only."
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "GithubActionsOnDevelopOnly"
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github[0].arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = merge(local.github_oidc_audience, {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:ref:refs/heads/develop"
        })
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ci_deploy_dev_readonly" {
  count      = var.enable_github_oidc ? 1 : 0
  role       = aws_iam_role.ci_deploy_dev[0].name
  policy_arn = "${local.arn}:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "ci_deploy_dev" {
  count = var.enable_github_oidc ? 1 : 0
  name  = "capstone-mortgage-ci-deploy-dev-policy"
  role  = aws_iam_role.ci_deploy_dev[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid      = "DevStateReadWrite"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.state.arn}/mortgage-platform/dev/*"
      },
      {
        Sid      = "DevStateLock"
        Effect   = "Allow"
        Action   = "s3:DeleteObject"
        Resource = "${aws_s3_bucket.state.arn}/mortgage-platform/dev/*.tflock"
      },
      {
        Sid      = "ListTheStateBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.state.arn
      },
      {
        Sid    = "ManageDevRolesNoManagedPolicies"
        Effect = "Allow"
        Action = [
          "iam:CreateRole", "iam:UpdateRole", "iam:UpdateRoleDescription", "iam:UpdateAssumeRolePolicy",
          "iam:TagRole", "iam:UntagRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:DetachRolePolicy",
        ]
        Resource = [for n in local.dev_role_names : "${local.arn}:iam::${local.account}:role/${n}"]
      },
      {
        Sid      = "PassDevRolesToTheirServicesOnly"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [for n in local.dev_role_names : "${local.arn}:iam::${local.account}:role/${n}"]
        Condition = {
          StringEquals = { "iam:PassedToService" = ["ecs-tasks.amazonaws.com", "lambda.amazonaws.com", "glue.amazonaws.com"] }
        }
      },
      {
        Sid    = "DevBucketsConfiguration"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket", "s3:PutBucket*", "s3:PutLifecycleConfiguration", "s3:PutEncryptionConfiguration",
          "s3:DeleteBucketPolicy",
        ]
        Resource = ["${local.arn}:s3:::capstone-mortgage-docs-dev", "${local.arn}:s3:::capstone-mortgage-analytics-dev"]
      },
      {
        Sid      = "GlueJobAssets"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:PutObjectTagging", "s3:GetObject", "s3:GetObjectTagging"]
        Resource = "${local.arn}:s3:::capstone-mortgage-analytics-dev/glue/*"
      },
      {
        Sid    = "DevTablesConfiguration"
        Effect = "Allow"
        Action = [
          "dynamodb:CreateTable", "dynamodb:UpdateTable", "dynamodb:UpdateTimeToLive", "dynamodb:UpdateContinuousBackups",
          "dynamodb:TagResource", "dynamodb:UntagResource",
        ]
        Resource = "${local.arn}:dynamodb:${local.region}:${local.account}:table/CapstoneMortgage*-dev"
      },
      {
        Sid    = "DevFunction"
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction", "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
          "lambda:AddPermission", "lambda:RemovePermission", "lambda:TagResource", "lambda:UntagResource",
        ]
        Resource = "${local.arn}:lambda:${local.region}:${local.account}:function:capstone-mortgage-*-dev"
      },
      {
        Sid      = "DevGlueJob"
        Effect   = "Allow"
        Action   = ["glue:CreateJob", "glue:UpdateJob", "glue:TagResource", "glue:UntagResource"]
        Resource = "${local.arn}:glue:${local.region}:${local.account}:job/capstone-mortgage-*-dev"
      },
      {
        Sid    = "DevLogGroups"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup", "logs:PutRetentionPolicy", "logs:TagResource", "logs:UntagResource",
          "logs:TagLogGroup", "logs:UntagLogGroup",
        ]
        Resource = flatten([for g in ["/aws/lambda/capstone-mortgage-*-dev", "/aws/events/capstone-mortgage-*-dev",
          "/ecs/capstone-mortgage-dev/*", "/aws-glue/python-jobs/*"] : [
          "${local.arn}:logs:${local.region}:${local.account}:log-group:${g}",
          "${local.arn}:logs:${local.region}:${local.account}:log-group:${g}:*",
        ]])
      },
      {
        Sid      = "PipelineAlertLogResourcePolicy"
        Effect   = "Allow"
        Action   = ["logs:PutResourcePolicy", "logs:DeleteResourcePolicy"]
        Resource = "*" # no resource-level permissions for these actions
      },
      {
        Sid      = "DevAlertRule"
        Effect   = "Allow"
        Action   = ["events:PutRule", "events:PutTargets", "events:RemoveTargets", "events:TagResource", "events:UntagResource"]
        Resource = "${local.arn}:events:${local.region}:${local.account}:rule/capstone-mortgage-*-dev-failed"
      },
      {
        Sid      = "DevAlarms"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricAlarm", "cloudwatch:TagResource", "cloudwatch:UntagResource"]
        Resource = "${local.arn}:cloudwatch:${local.region}:${local.account}:alarm:capstone-mortgage-*-dev-*"
      },
      {
        Sid    = "DevMessaging"
        Effect = "Allow"
        Action = [
          "sns:CreateTopic", "sns:SetTopicAttributes", "sns:Subscribe", "sns:Unsubscribe",
          "sns:SetSubscriptionAttributes", "sns:TagResource", "sns:UntagResource",
          "sqs:CreateQueue", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:UntagQueue",
        ]
        Resource = [
          "${local.arn}:sns:${local.region}:${local.account}:capstone-mortgage-*-dev",
          "${local.arn}:sns:${local.region}:${local.account}:capstone-mortgage-*-dev:*",
          "${local.arn}:sqs:${local.region}:${local.account}:capstone-mortgage-*-dev",
        ]
      },
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "DevImagesPushAndRepositories"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
          "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:CreateRepository",
          "ecr:PutLifecyclePolicy", "ecr:PutImageScanningConfiguration", "ecr:PutImageTagMutability",
          "ecr:TagResource", "ecr:UntagResource",
        ]
        Resource = "${local.arn}:ecr:${local.region}:${local.account}:repository/capstone-mortgage-dev/*"
      },
      {
        Sid    = "DevClusterAndServices"
        Effect = "Allow"
        Action = [
          "ecs:CreateCluster", "ecs:UpdateCluster", "ecs:UpdateClusterSettings", "ecs:CreateService", "ecs:UpdateService",
          "ecs:TagResource", "ecs:UntagResource",
        ]
        Resource = [
          "${local.arn}:ecs:${local.region}:${local.account}:cluster/capstone-mortgage-dev",
          "${local.arn}:ecs:${local.region}:${local.account}:service/capstone-mortgage-dev/*",
          "${local.arn}:ecs:${local.region}:${local.account}:task-definition/capstone-mortgage-dev-*:*",
        ]
      },
      {
        Sid      = "TaskDefinitionRevisions"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:DeregisterTaskDefinition"]
        Resource = "*" # register/deregister have no resource-level permissions
      },
      {
        Sid    = "NetworkingOfThisProjectOnly"
        Effect = "Allow"
        Action = [
          "ec2:CreateSubnet", "ec2:CreateRouteTable", "ec2:CreateSecurityGroup", "ec2:CreateRoute", "ec2:ReplaceRoute",
          "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable", "ec2:AttachInternetGateway", "ec2:ModifyVpcAttribute",
          "ec2:ModifySubnetAttribute", "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress", "ec2:ModifySecurityGroupRules",
          "ec2:UpdateSecurityGroupRuleDescriptionsIngress", "ec2:UpdateSecurityGroupRuleDescriptionsEgress",
          "ec2:CreateTags", "ec2:DeleteTags",
        ]
        Resource  = "*"
        Condition = { StringEquals = { "aws:ResourceTag/Project" = "mortgage-intelligence" } }
      },
      {
        Sid    = "NewNetworkingMustBeTagged"
        Effect = "Allow"
        Action = [
          "ec2:CreateVpc", "ec2:CreateSubnet", "ec2:CreateInternetGateway", "ec2:CreateRouteTable",
          "ec2:CreateSecurityGroup", "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
          "ec2:CreateTags",
        ]
        Resource  = "*"
        Condition = { StringEquals = { "aws:RequestTag/Project" = "mortgage-intelligence" } }
      },
    ], local.deny_business_data_reads)
  })
}

# ---------------------------------------------------------------- values for the GitHub repository secrets
output "github_secret_AWS_PLAN_ROLE_ARN" {
  description = "Repository secret AWS_PLAN_ROLE_ARN."
  value       = one(aws_iam_role.ci_plan[*].arn)
}

output "github_secret_AWS_DEPLOY_DEV_ROLE_ARN" {
  description = "Repository secret AWS_DEPLOY_DEV_ROLE_ARN."
  value       = one(aws_iam_role.ci_deploy_dev[*].arn)
}

output "github_secret_TF_DEVELOPER_PRINCIPAL_ARN" {
  description = "Repository secret TF_DEVELOPER_PRINCIPAL_ARN: the developer role trusted by the app roles (run bootstrap from your own session)."
  value       = data.aws_iam_session_context.current.issuer_arn
}
