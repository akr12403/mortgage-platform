"""docs/ai/prompt-library.md must show the production prompt exactly (Task 7.5: no drift between docs and code).

Runs where the whole repository is checked out (CI, a local clone). The Docker test image contains only this
service, so the check is skipped there.
"""
import re

import pytest

from src.ops.prompts import INCIDENT_PROMPT_VERSION, INCIDENT_SYSTEM_PROMPT
from src.rag.prompts import ASK_PROMPT_VERSION, ASK_SYSTEM_PROMPT
from tests.conftest import SERVICE_ROOT

LIBRARY = SERVICE_ROOT.parent.parent / "docs" / "ai" / "prompt-library.md"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.skipif(not LIBRARY.exists(), reason="docs/ not available (service-only checkout)")
@pytest.mark.parametrize("version, prompt", [(ASK_PROMPT_VERSION, ASK_SYSTEM_PROMPT),
                                             (INCIDENT_PROMPT_VERSION, INCIDENT_SYSTEM_PROMPT)])
def test_documented_prompts_match_the_code(version, prompt):
    doc = LIBRARY.read_text(encoding="utf-8")
    pattern = rf"<!-- prompt:{re.escape(version)}:start -->\s*```text\n(.*?)```\s*<!-- prompt:{re.escape(version)}:end -->"
    block = re.search(pattern, doc, re.S)
    assert block, f"{version} prompt block markers not found in docs/ai/prompt-library.md"
    assert _normalise(block.group(1)) == _normalise(prompt)
    assert f"`{version}`" in doc


@pytest.mark.skipif(not LIBRARY.exists(), reason="docs/ not available (service-only checkout)")
def test_library_has_at_least_five_templates():
    rows = re.findall(r"^\| \[`([a-z0-9-]+-v\d+)`\]", LIBRARY.read_text(encoding="utf-8"), re.M)
    assert len(rows) >= 5 and len(rows) == len(set(rows))
