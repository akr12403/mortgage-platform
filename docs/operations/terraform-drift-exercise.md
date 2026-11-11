# Drift detection exercise (M9 Task 9.2, step 4)

The handbook's exercise is: make a manual change, see the diff in `terraform plan`, then remediate through code. [`scripts/terraform/drift-demo.sh`](../../scripts/terraform/drift-demo.sh) runs it end to end on dev, and each step checks Terraform's exit code.

```bash
aws login --profile capstone-dev --region us-east-2
bash scripts/terraform/drift-demo.sh          # asks before each change; --yes to skip the prompts
```

| Step | What happens | Must see |
| --- | --- | --- |
| 0. Baseline | `terraform plan -detailed-exitcode` | exit **0**: dev matches the code |
| 1. Manual change, the "console hotfix" | Lambda `capstone-mortgage-doc-processor-dev` memory set from **256 to 512 MB**, and **`AmazonS3ReadOnlyAccess` attached to `mortgage-api-role`** | done outside Terraform with the AWS CLI |
| 2. Detect | `terraform plan -detailed-exitcode` | exit **2**: `memory_size = 512 -> 256` on the function, and the extra policy on `aws_iam_role_policy_attachments_exclusive` (`policy_arns` back to `[]`) |
| 3. Remediate via code | `terraform apply` | Terraform puts back what the code says. It doesn't absorb the hotfix. |
| 4. Verify | plan again, then read both values from AWS | exit **0**, memory **256 MB**, **0** managed policies on the role |

The plans are saved in `reports/terraform/drift-*.txt`. That folder is git-ignored because the plans contain ARNs with the account id.

## Why these two changes

- **Memory 256 → 512 MB** is ordinary configuration drift. It's harmless-looking and doubles cost, and a later apply would silently undo it unless someone noticed.
- **A managed policy on `mortgage-api-role`** is security drift. That role may only publish to one SNS topic (M8 Task 8.1). Read access to every bucket in the account would break least privilege. A plain `aws_iam_role` resource wouldn't notice an attached policy. The `*_exclusive` resources in `modules/security` make Terraform own the complete set, so the plan shows it.

## Remediation choices

When a plan shows drift, decide which side is right:

| The manual change was… | Do |
| --- | --- |
| a mistake or unapproved change, like this exercise | `terraform apply` to restore the code's values |
| a real fix that should stay | change the code (or the template in `infrastructure/aws/`), open a PR, let CI plan it, merge, then apply. The code becomes the source again. |
| made in an emergency | the same as above, within one working day. Note it in the incident record (Task 9.4). |

Nobody runs `terraform apply -refresh-only` to "accept" drift without a code change. That would make the state agree with AWS while the code still disagrees.

## Record of the run

Run on dev on 2026-11-09 by akr12403, right after the M8 import (`48 imported, 44 added, 21 changed, 0 destroyed`, follow-up plan exit 0). This is the script's output, with the session line (account id) left out:

```text
== 0. Baseline: dev must match the code before the exercise ==
  OK   no changes (exit 0)
== 1. Manual changes outside Terraform (simulated console hotfix) ==
  OK   Lambda memory 256 -> 512 MB
  OK   mortgage-api-role: attached arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
== 2. Detect: terraform plan ==
      # module.compute.aws_lambda_function.doc_processor will be updated in-place
          ~ memory_size                    = 512 -> 256
      # module.security.aws_iam_role_policy_attachments_exclusive.app["mortgage-api-role"] will be updated in-place
          ~ policy_arns = [
              - "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
    Plan: 0 to add, 2 to change, 0 to destroy.
  OK   drift detected (exit 2): Lambda memory and the extra managed policy
== 3. Remediate via code: terraform apply ==
    Apply complete! Resources: 0 added, 2 changed, 0 destroyed.
== 4. Verify ==
  OK   plan clean (exit 0); Lambda memory 256 MB; mortgage-api-role has 0 managed policies
```

Scheduled drift detection, a nightly `plan -detailed-exitcode` that alerts on exit 2, is a CI job in Task 9.1 part B.
