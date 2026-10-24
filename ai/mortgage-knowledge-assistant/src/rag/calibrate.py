"""Measure retrieval quality and pick the similarity threshold from evidence (Task 7.3 "tune and record").

    python -m src.rag.calibrate

Embeds a fixed set of on-corpus questions (each with the document(s) that should answer it) and off-corpus
questions, retrieves top-k for each, and prints:
- hit@k: how often an expected document is in the top k;
- the best similarity per question;
- a suggested threshold halfway between the weakest on-corpus best match and the strongest off-corpus one.
Only embedding calls are made (no LLM), so a run costs a tiny fraction of a cent.
"""
from __future__ import annotations

import sys

from src.config import ConfigError, load_settings
from src.embeddings import EmbeddingError
from src.rag.factory import build_retriever
from src.store.vector_store import PgVectorStore, VectorStoreError

ON_CORPUS: tuple[tuple[str, frozenset[str]], ...] = (
    ("What happens when a payment is 30 days late?", frozenset({"delinquency-playbook"})),
    ("What is the delinquency contact timeline?", frozenset({"delinquency-playbook"})),
    ("When does a delinquent loan become SEVERE?", frozenset({"delinquency-playbook"})),
    ("What credit score is needed for an FHA loan?", frozenset({"underwriting-guidelines"})),
    ("When does an application need a second underwriting review?", frozenset({"underwriting-guidelines"})),
    ("How do I avoid creating a duplicate payment when I retry?", frozenset({"servicing-faq"})),
    ("Why am I getting a 429 error?", frozenset({"servicing-faq"})),
    ("Can I paste borrower details into an AI tool?", frozenset({"security-policy-excerpt", "servicing-faq"})),
    ("What are the mortgage statuses and how is each one reached?", frozenset({"mortgage-policy-overview"})),
    ("How is borrower data classified?", frozenset({"security-policy-excerpt"})),
    ("Who is allowed to approve or decline a loan?",
     frozenset({"mortgage-policy-overview", "underwriting-guidelines", "security-policy-excerpt"})),
)

OFF_CORPUS: tuple[str, ...] = (
    "What is the capital of France?",
    "Write a short poem about the ocean.",
    "What is today's 30-year fixed mortgage rate?",
    "How do I restart a Kubernetes deployment?",
    "Who won the 2022 football World Cup?",
    "Which stock should I buy this week?",
)


def suggest_threshold(on_best: list[float], off_best: list[float]) -> tuple[float | None, str]:
    weakest_on, strongest_off = min(on_best), max(off_best)
    if weakest_on <= strongest_off:
        return None, (f"on- and off-corpus scores overlap (weakest on-corpus {weakest_on:.3f} <= strongest "
                      f"off-corpus {strongest_off:.3f}); no single threshold separates them. Rely on the LLM's "
                      "'sufficient' check as the second gate and pick a threshold that keeps every on-corpus hit.")
    midpoint = round((weakest_on + strongest_off) / 2, 2)
    return midpoint, (f"separation: weakest on-corpus {weakest_on:.3f} > strongest off-corpus {strongest_off:.3f}; "
                      f"suggested RAG_SIMILARITY_THRESHOLD={midpoint}")


def main() -> int:
    store = None
    try:
        settings = load_settings()
        store = PgVectorStore(settings)
        retriever = build_retriever(settings, store)
        print(f"model {settings.embedding_model}, corpus {settings.knowledge_version}, top-k {settings.top_k}, "
              f"current threshold {settings.similarity_threshold}\n")
        on_best, hits = [], 0
        print("ON-CORPUS (expected document in top-k?)")
        for question, expected in ON_CORPUS:
            r = retriever.retrieve(question)
            found = any(h.doc_id in expected for h in r.hits)
            hits += found
            on_best.append(r.top_similarity)
            top = r.hits[0].chunk_id if r.hits else "-"
            print(f"  {'HIT ' if found else 'MISS'} best {r.top_similarity:.3f}  {top:<38} {question}")
        off_best = []
        print("\nOFF-CORPUS (should fall below the threshold)")
        for question in OFF_CORPUS:
            r = retriever.retrieve(question)
            off_best.append(r.top_similarity)
            top = r.hits[0].chunk_id if r.hits else "-"
            print(f"       best {r.top_similarity:.3f}  {top:<38} {question}")
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (EmbeddingError, VectorStoreError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()

    print(f"\nhit@{settings.top_k}: {hits}/{len(ON_CORPUS)}")
    threshold, message = suggest_threshold(on_best, off_best)
    print(message)
    current = settings.similarity_threshold
    kept = sum(s >= current for s in on_best)
    leaked = sum(s >= current for s in off_best)
    print(f"with the current threshold {current}: {kept}/{len(on_best)} on-corpus answered, "
          f"{leaked}/{len(off_best)} off-corpus would reach the LLM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
