"""docs/ai/prompt-library.md must show the production prompt exactly (Task 7.5: no drift between docs and code).

Runs where the whole repository is checked out (CI, a local clone). The Docker test image contains only this
service, so the check is skipped there.
"""
import re

import pytest

from src.rag.prompts import ASK_PROMPT_VERSION, ASK_SYSTEM_PROMPT
from tests.conftest import SERVICE_ROOT

LIBRARY = SERVICE_ROOT.parent.parent / "docs" / "ai" / "prompt-library.md"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.skipif(not LIBRARY.exists(), reason="docs/ not available (service-only checkout)")
def test_documented_ask_prompt_matches_the_code():
    doc = LIBRARY.read_text(encoding="utf-8")
    block = re.search(r"<!-- prompt:ask-v1:start -->\s*```text\n(.*?)```\s*<!-- prompt:ask-v1:end -->", doc, re.S)
    assert block, "ask-v1 prompt block markers not found in docs/ai/prompt-library.md"
    assert _normalise(block.group(1)) == _normalise(ASK_SYSTEM_PROMPT)
    assert f"`{ASK_PROMPT_VERSION}`" in doc


@pytest.mark.skipif(not LIBRARY.exists(), reason="docs/ not available (service-only checkout)")
def test_library_has_at_least_five_templates():
    rows = re.findall(r"^\| \[`([a-z0-9-]+-v\d+)`\]", LIBRARY.read_text(encoding="utf-8"), re.M)
    assert len(rows) >= 5 and len(rows) == len(set(rows))
