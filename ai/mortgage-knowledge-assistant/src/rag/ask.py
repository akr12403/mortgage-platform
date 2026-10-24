"""Ask one question from the command line (Task 7.3, before the HTTP API exists).

    python -m src.rag.ask "What is the delinquency contact timeline?"
    python -m src.rag.ask --loan-type FHA "What credit score is required?"
    python -m src.rag.ask --debug "..."     # also prints the retrieved chunks and similarities

Prints the same JSON body POST /api/v1/assistant/ask will return. Exit codes: 0 ok, 2 bad input/config, 1 failure.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid

from src.config import ConfigError, load_settings
from src.embeddings import EmbeddingError
from src.ingest.loader import LOAN_TYPES
from src.rag.factory import build_service
from src.rag.llm import LLMError
from src.rag.service import QuestionError
from src.store.vector_store import PgVectorStore, VectorStoreError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.rag.ask", description="Ask the knowledge assistant.")
    parser.add_argument("question")
    parser.add_argument("--loan-type", choices=LOAN_TYPES, help="only use passages tagged ALL or this loan type")
    parser.add_argument("--mortgage-id", help="business id, e.g. MTG-1002 (used for approval rules and logs only)")
    parser.add_argument("--debug", action="store_true", help="print retrieved chunks and similarities")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    correlation_id = str(uuid.uuid4())
    store = None
    try:
        settings = load_settings()
        store = PgVectorStore(settings)
        result = build_service(settings, store).ask(args.question, args.loan_type, args.mortgage_id, correlation_id)
    except (ConfigError, QuestionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (EmbeddingError, VectorStoreError, LLMError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()

    print(json.dumps(result.as_api(correlation_id), indent=2))
    if args.debug:
        print(f"\nthreshold {settings.similarity_threshold}, top-k {settings.top_k}, model {result.model or '(not called)'}, "
              f"prompt {result.prompt_version}, insufficient={result.insufficient_context}")
        for chunk_id, similarity in result.retrieved:
            mark = "*" if any(c.chunk_id == chunk_id for c in result.citations) else " "
            print(f" {mark} {similarity:.3f}  {chunk_id}")
        if result.approval_reasons:
            print(f"approval reasons: {', '.join(result.approval_reasons)}")
        if result.dropped_citations:
            print(f"dropped invented citations: {', '.join(result.dropped_citations)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
