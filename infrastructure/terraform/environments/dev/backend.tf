# Remote state: S3 with native locking (a <key>.tflock object, Terraform 1.10+). No DynamoDB lock table: Terraform
# deprecated DynamoDB locking for the S3 backend (docs/operations/terraform.md#deviations-from-the-handbook).
# The bucket name contains the account id, so it is not committed: scripts/terraform/tf.sh passes it at init
# (-backend-config=bucket=capstone-mortgage-tfstate-<account>). The bucket comes from infrastructure/terraform/bootstrap.
terraform {
  backend "s3" {
    key          = "mortgage-platform/dev/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
