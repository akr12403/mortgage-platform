"""Ingestion command.

    python -m src.ingest                 # ingest knowledge/$KNOWLEDGE_VERSION (default v1) into pgvector
    python -m src.ingest --dry-run       # load + chunk only: no API calls, no database
    python -m src.ingest --dry-run --show-chunks

Exit codes: 0 success, 2 configuration or corpus error, 1 embedding or database failure.
"""
from __future__ import annotations

import argparse
import logging
import sys

from src.config import ConfigError, load_settings
from src.embeddings import EmbeddingError, build_embedder
from src.ingest.loader import CorpusError
from src.ingest.pipeline import ingest
from src.ingest.tokenizer import get_tokenizer
from src.store.vector_store import PgVectorStore, VectorStoreError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.ingest", description="Ingest the knowledge corpus.")
    parser.add_argument("--version", help="corpus version folder, e.g. v1 (default: KNOWLEDGE_VERSION or v1)")
    parser.add_argument("--dry-run", action="store_true", help="load and chunk only; no embedding API, no database")
    parser.add_argument("--show-chunks", action="store_true", help="print each chunk id, section and token count")
    parser.add_argument("--tokenizer", choices=("tiktoken", "simple"), default="tiktoken",
                        help="'simple' approximates tokens by words; allowed only with --dry-run")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    try:
        settings = load_settings()
        if args.version:
            from dataclasses import replace
            settings = replace(settings, knowledge_version=args.version)
        if args.tokenizer == "simple" and not args.dry_run:
            raise ConfigError("--tokenizer simple is only for --dry-run; real ingests must count real tokens")
        tokenizer = get_tokenizer(args.tokenizer)
        embedder = store = None
        if not args.dry_run:
            embedder = build_embedder(settings)
            store = PgVectorStore(settings)
        try:
            report, chunks = ingest(settings.corpus_dir, tokenizer, embedder, store,
                                    chunk_size=settings.chunk_size_tokens,
                                    chunk_overlap=settings.chunk_overlap_tokens, dry_run=args.dry_run)
        finally:
            if store is not None:
                store.close()
    except (ConfigError, CorpusError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (EmbeddingError, VectorStoreError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.show_chunks:
        for c in chunks:
            print(f"{c.chunk_id:<40} {c.token_count:>4} tokens  {','.join(c.loan_types):<20} {c.section}")
    print(f"Tokenizer {tokenizer.name}, chunk size {settings.chunk_size_tokens}, "
          f"overlap {settings.chunk_overlap_tokens}" + ("" if args.dry_run else f", model {embedder.model}"))
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
