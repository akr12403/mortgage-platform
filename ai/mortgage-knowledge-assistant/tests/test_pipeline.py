import pytest

from src.embeddings import EmbeddingError, FakeEmbedder
from src.ingest.pipeline import ingest
from src.ingest.tokenizer import SimpleTokenizer
from src.store.vector_store import InMemoryVectorStore
from tests.conftest import write_doc

TOK = SimpleTokenizer()


class CountingEmbedder(FakeEmbedder):
    def __init__(self, model="fake-a"):
        super().__init__(dimensions=16, model=model)
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return super().embed(texts)


def _corpus(tmp_path):
    folder = tmp_path / "v1"
    write_doc(folder, "delinquency-playbook", "## Timeline\n\nDay 30 is delinquent.\n\n## Cure\n\nAll posted.\n")
    write_doc(folder, "servicing-faq", "## Payments\n\nUse an Idempotency-Key.\n")
    return folder


def test_first_ingest_embeds_and_stores_every_chunk_with_metadata(tmp_path):
    store, embedder = InMemoryVectorStore(), CountingEmbedder()
    report, chunks = ingest(_corpus(tmp_path), TOK, embedder, store)
    assert (report.documents, report.chunks, report.embedded, report.unchanged, report.deleted) == (2, 3, 3, 0, 0)
    assert store.count("v1") == 3 and store.commits == 1
    row = store.rows["delinquency-playbook:v1:c-01"]
    assert row.chunk.section == "Timeline" and row.chunk.doc_file == "delinquency-playbook.md"
    assert row.chunk.loan_types == ("ALL",) and row.embedding_model == "fake-a" and len(row.embedding) == 16


def test_rerun_of_unchanged_corpus_makes_no_embedding_calls(tmp_path):
    folder, store = _corpus(tmp_path), InMemoryVectorStore()
    ingest(folder, TOK, CountingEmbedder(), store)
    embedder = CountingEmbedder()
    report, _ = ingest(folder, TOK, embedder, store)
    assert embedder.calls == [] and (report.embedded, report.unchanged, report.deleted) == (0, 3, 0)


def test_only_changed_chunks_are_re_embedded(tmp_path):
    folder, store = _corpus(tmp_path), InMemoryVectorStore()
    ingest(folder, TOK, CountingEmbedder(), store)
    write_doc(folder, "servicing-faq", "## Payments\n\nAlways send an Idempotency-Key header.\n")
    embedder = CountingEmbedder()
    report, _ = ingest(folder, TOK, embedder, store)
    assert report.embedded == 1 and report.unchanged == 2
    assert "Always send" in embedder.calls[0][0]


def test_changing_embedding_model_re_embeds_everything(tmp_path):
    folder, store = _corpus(tmp_path), InMemoryVectorStore()
    ingest(folder, TOK, CountingEmbedder("fake-a"), store)
    report, _ = ingest(folder, TOK, CountingEmbedder("fake-b"), store)
    assert report.embedded == 3
    assert {r.embedding_model for r in store.rows.values()} == {"fake-b"}


def test_removed_documents_and_sections_are_deleted(tmp_path):
    folder, store = _corpus(tmp_path), InMemoryVectorStore()
    ingest(folder, TOK, CountingEmbedder(), store)
    (folder / "servicing-faq.md").unlink()
    write_doc(folder, "delinquency-playbook", "## Timeline\n\nDay 30 is delinquent.\n")
    report, _ = ingest(folder, TOK, CountingEmbedder(), store)
    assert report.deleted == 2 and set(store.rows) == {"delinquency-playbook:v1:c-01"}


def test_versions_are_independent(tmp_path):
    store = InMemoryVectorStore()
    ingest(_corpus(tmp_path), TOK, CountingEmbedder(), store)
    v2 = tmp_path / "v2"
    write_doc(v2, "delinquency-playbook", "## Timeline\n\nNew wording.\n")
    report, _ = ingest(v2, TOK, CountingEmbedder(), store)
    assert report.deleted == 0 and store.count("v1") == 3 and store.count("v2") == 1


def test_dry_run_needs_no_embedder_or_store(tmp_path):
    report, chunks = ingest(_corpus(tmp_path), TOK, None, None, dry_run=True)
    assert report.dry_run and report.chunks == len(chunks) == 3 and report.embedded == 0


def test_embedding_failure_rolls_back_and_stores_nothing(tmp_path):
    class Failing(CountingEmbedder):
        def embed(self, texts):
            raise EmbeddingError("embedding API returned HTTP 500: boom")

    class RecordingStore(InMemoryVectorStore):
        rolled_back = False

        def rollback(self):
            self.rolled_back = True

    store = RecordingStore()
    with pytest.raises(EmbeddingError):
        ingest(_corpus(tmp_path), TOK, Failing(), store)
    assert store.rolled_back and store.commits == 0 and store.count("v1") == 0


def test_without_embedder_a_real_run_is_refused(tmp_path):
    with pytest.raises(ValueError, match="required unless dry_run"):
        ingest(_corpus(tmp_path), TOK, None, InMemoryVectorStore())
