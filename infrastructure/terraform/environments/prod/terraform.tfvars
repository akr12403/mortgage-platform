# prod: plan-only (CI shows the plan behind a manual approval; it is never applied in the sandbox).
# sandbox_teardown stays false: buckets and image repositories are never force-deleted in prod.
environment   = "prod"
vpc_cidr      = "10.42.0.0/16"
desired_count = 0
