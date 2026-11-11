# Engineering Standards & Git Conventions

## 1. Branching Strategy & Workflow
We follow a GitFlow-inspired branching strategy:
- **`main`**: Production-ready code. Direct commits are strictly prohibited.
- **`develop`**: Primary integration branch for active development. Direct commits are strictly prohibited.
- **`feature/<ticket-or-milestone>-<short-description>`**: Topic branches created off `develop`.
- **`fix/<description>`**: Bug fix branches targeted at resolving issues in `develop`.

# Engineering Standards & Code Review Checklist

## Code Review Checklist
Before any Pull Request can be merged to `develop` or `main`, reviewers must verify:
- [ ] **Security**: No hardcoded credentials, API keys, or connection strings; inputs are parameterized/validated.
- [ ] **Tests**: Unit or integration tests are included or updated; all CI checks pass.
- [ ] **No Secrets**: Secret scanning reports zero leaks.
- [ ] **Migration Review**: Database schema changes include rollback/idempotency safety checks and are verified via local seed/reset scripts.

### Branch Naming Pattern
- `feature/<ticket-or-milestone>-<short-description>`
- Example: `feature/M1-repository-setup`

## 2. Commit Message Standards
We follow the Conventional Commits specification: `type(scope): summary`

### Types
- `docs`: Updates to documentation (e.g., requirements, architecture, standards)
- `chore`: Repository configuration, directory structure, `.gitignore` updates
- `feat`: New feature or service code (Milestone 3+)
- `fix`: Bug fixes

### Example Commit Messages
- `chore(repo): add root .gitignore and folder structure`
- `docs(requirements): create team charter and standards`
- `docs(architecture): add initial system context diagram`

## 3. Pull Request & Review Process
1. Create a feature branch off `develop`.
2. Commit changes using Conventional Commit standards.
3. Push branch to remote and open a Pull Request (PR) targeting `develop`.
4. Obtain at least **1 peer review** approval.
5. Merge PR into `develop` using Squash/Rebase merge.
6. Delete the remote feature branch after merging.

## 4. Security & Safety Rules
- **No Secrets**: Never commit `.env` files, passwords, API keys, or private SSH keys.
- **No Real Borrower Data**: Synthetic/fake data only across all environments and test cases.

## 5. Target Execution Environment Baseline
The project supports local execution on macOS (ARM64) and testing on the target Windows VM environment:

| Tool | Target VM Version | Role / Scope | Notes |
| --- | --- | --- | --- |
| **Git** | `2.52.0.windows.1` | Source Control | Standardized via `.gitattributes` |
| **Java JDK** | `17.0.12 LTS` | Backend Services | Target LTS Java version |
| **Python** | `3.14.7` | Analytics & AI | Microservices runtime |
| **Docker Engine** | `29.7.2` | Containerization | Architecture-agnostic images |
| **PostgreSQL CLI** | `17.7` | Database | Match `postgres:17.7` container |

### Cross-Platform Rules
- **Line Endings**: Enforced via `.gitattributes` (`LF` for scripts and standard text).
- **Paths**: Use standard relative POSIX paths (`/`) across all scripts, code, and configurations.
- **Docker**: Base images must be architecture-agnostic (`amd64` / `arm64`).
