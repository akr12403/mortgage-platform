// Cucumber configuration (M10 Task 10.2). Run from tests/e2e: `npm test`, or one journey: `npm test -- --tags @J2`.
// Reports go to the repo-level reports/ folder (git-ignored), where CI collects them:
//   reports/e2e/cucumber-report.html   HTML report (CI artifact)
//   reports/junit/e2e-cucumber.xml     JUnit, for the pipeline's test summary
export default {
  paths: ["features/**/*.feature"],
  import: ["support/**/*.mjs", "steps/**/*.mjs"],
  format: [
    "progress",
    "summary",
    "html:../../reports/e2e/cucumber-report.html",
    "junit:../../reports/junit/e2e-cucumber.xml",
  ],
  formatOptions: { junit: { suiteName: "e2e" } },
  // Scenarios are independent (each creates its own borrower and mortgage), so they can run in parallel.
  parallel: Number(process.env.E2E_PARALLEL ?? 2),
  // One retry for timing flakiness in the asynchronous event flow; a scenario that needed it is shown as flaky.
  retry: Number(process.env.E2E_RETRY ?? 1),
  strict: true,
};
