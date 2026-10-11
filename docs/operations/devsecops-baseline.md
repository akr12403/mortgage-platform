# DevSecOps Baseline Report (Task 2.6)

## Repository Security Settings (GitHub)
- **Branch Protection**: Enabled on `main` and `develop`
  - Require pull request reviews before merging
  - Dismiss stale pull request approvals when new commits are pushed
  - Restrict force pushes and deletions
- **Secret Scanning**: Enabled to prevent accidental credential commits.
- **Dependency Management (SCA)**: Utilizing manual `pip audit` / dependency review protocol until Milestone 9 CI integration.

## Pipeline Validation
- Root `.gitlab-ci.yml` stub validated with `validate` stage secret detection hooks[cite: 4].