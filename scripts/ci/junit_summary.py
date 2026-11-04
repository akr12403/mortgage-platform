"""Summarise JUnit XML files as a Markdown table (for $GITHUB_STEP_SUMMARY).

    python3 scripts/ci/junit_summary.py "<title>" reports/junit >> "$GITHUB_STEP_SUMMARY"

Stdlib only. Prints one row per XML file (tests, failures, errors, skipped, time) and lists up to 10 failing tests.
Never fails the job: the test step itself decides pass/fail.
XML safety (Semgrep use-defused-xml-parse): the input is JUnit XML written by this run's own test tools, and any
file that declares a DTD or entities is refused before parsing (that is what defusedxml blocks: XXE, entity
expansion), so the stdlib parser never sees external or nested entities. No extra dependency on the runner.
"""
import glob
import os
import sys
import xml.etree.ElementTree as ET


def safe_parse(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity declarations are not allowed in JUnit reports")
    # nosemgrep: python.lang.security.use-defused-xml-parse.use-defused-xml-parse -- DTDs/entities rejected above
    return ET.fromstring(data)


def suites(root):
    return [root] if root.tag == "testsuite" else root.findall("testsuite")


def main():
    title, folder = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(folder, "*.xml")))
    print(f"### {title}\n")
    if not files:
        print("_No JUnit reports were produced._\n")
        return
    print("| Report | Tests | Failed | Errors | Skipped | Time (s) |\n| --- | ---: | ---: | ---: | ---: | ---: |")
    failing = []
    totals = [0, 0, 0, 0, 0.0]
    for path in files:
        try:
            root = safe_parse(path)
        except (ET.ParseError, ValueError):
            print(f"| `{os.path.basename(path)}` | unreadable | | | | |")
            continue
        t = f = e = s = 0
        secs = 0.0
        for suite in suites(root):
            t += int(suite.get("tests", 0))
            f += int(suite.get("failures", 0))
            e += int(suite.get("errors", 0))
            s += int(suite.get("skipped", 0))
            secs += float(suite.get("time", 0) or 0)
            for case in suite.iter("testcase"):
                if case.find("failure") is not None or case.find("error") is not None:
                    failing.append(f"{case.get('classname', '')}.{case.get('name', '')}")
        for i, v in enumerate((t, f, e, s, secs)):
            totals[i] += v
        print(f"| `{os.path.basename(path)}` | {t} | {f} | {e} | {s} | {secs:.1f} |")
    print(f"| **total** | **{totals[0]}** | **{totals[1]}** | **{totals[2]}** | **{totals[3]}** | {totals[4]:.1f} |\n")
    if failing:
        print("Failing tests:\n")
        for name in failing[:10]:
            print(f"- `{name}`")
        print()


if __name__ == "__main__":
    main()
