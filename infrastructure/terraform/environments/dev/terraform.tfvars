# dev: the only environment that is applied in the sandbox. No secrets, no account id, no personal IP here.
environment                   = "dev"
vpc_cidr                      = "10.40.0.0/16"
desired_count                 = 0    # scale to 1 for a demo: bash scripts/terraform/tf.sh dev apply -var desired_count=1 ...
sandbox_teardown              = true # sandbox: terraform destroy may delete non-empty buckets / ECR repositories
manage_account_wide_resources = true # dev owns the account-wide Glue python-jobs log groups
