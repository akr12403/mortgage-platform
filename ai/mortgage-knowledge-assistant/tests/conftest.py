import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


@pytest.fixture
def corpus_v1() -> Path:
    return SERVICE_ROOT / "knowledge" / "v1"


def write_doc(folder: Path, doc_id: str, body: str, *, version: str | None = None,
              loan_types: str = "[ALL]", title: str | None = None) -> Path:
    """Write a minimal valid corpus document for tests."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{doc_id}.md"
    path.write_text(
        "---\n"
        f"docId: {doc_id}\n"
        f"title: {title or doc_id.replace('-', ' ').title()}\n"
        f"version: {version or folder.name}\n"
        f"loanTypes: {loan_types}\n"
        "owner: Test owner\n"
        "classification: Internal (synthetic training policy)\n"
        "lastReviewed: 2026-10-24\n"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return path
