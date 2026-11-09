# infrastructure/terraform (M9 Task 9.2)

The AWS platform as code: 5 modules (networking, security, storage, compute, messaging) and 3 environments. dev is applied, and imports the M8 resources; test and prod are plan-only. State lives in S3 with native locking.

```bash
bash scripts/terraform/tf.sh bootstrap init && bash scripts/terraform/tf.sh bootstrap apply   # once: state bucket
bash scripts/terraform/tf.sh dev init
bash scripts/terraform/tf.sh dev plan -out=dev.tfplan && bash scripts/terraform/tf.sh dev apply dev.tfplan
python3 tests/infrastructure/test_terraform_layout.py                                         # static checks (CI)
```

Guide, design decisions, cost and deviations: [docs/operations/terraform.md](../../docs/operations/terraform.md). Drift exercise: [docs/operations/terraform-drift-exercise.md](../../docs/operations/terraform-drift-exercise.md).

IAM, S3 and DynamoDB definitions are **not** duplicated here. The modules render the templates in [`../aws/`](../aws/).
