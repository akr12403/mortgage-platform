from src.embeddings import FakeEmbedder
from src.ingest.pipeline import ingest
from src.ingest.tokenizer import SimpleTokenizer
from src.rag.retriever import Retriever
from src.store.vector_store import InMemoryVectorStore
from tests.conftest import write_doc

EMB = FakeEmbedder(dimensions=512)


def _store(tmp_path):
    folder = tmp_path / "v1"
    write_doc(folder, "delinquency-playbook",
              "## Timeline\n\ndelinquency contact timeline day 30 phone call notice\n\n"
              "## Cure\n\ncure reinstatement all installments posted\n")
    write_doc(folder, "underwriting-guidelines",
              "## General criteria\n\ndebt to income ratio 43 percent\n\n"
              "## FHA loans\n<!-- loanType: FHA -->\n\nfha minimum credit score 580\n\n"
              "## VA loans\n<!-- loanType: VA -->\n\nva minimum credit score 620\n",
              loan_types="[CONVENTIONAL, FHA, VA]")
    store = InMemoryVectorStore()
    ingest(folder, SimpleTokenizer(), EMB, store)
    return store


def test_returns_best_match_first_with_similarity(tmp_path):
    r = Retriever(EMB, _store(tmp_path), "v1", top_k=3, threshold=0.0).retrieve("delinquency contact timeline")
    assert r.hits[0].chunk_id == "delinquency-playbook:v1:c-01" and r.hits[0].section == "Timeline"
    assert [h.similarity for h in r.hits] == sorted((h.similarity for h in r.hits), reverse=True)
    assert len(r.hits) == 3


def test_threshold_gates_the_question_and_passes_all_top_k_as_context(tmp_path):
    r = Retriever(EMB, _store(tmp_path), "v1", top_k=5, threshold=0.3).retrieve("delinquency contact timeline")
    assert r.sufficient and r.top_similarity >= 0.3
    assert r.relevant == r.hits  # weaker chunks are kept: the answer may sit just under the threshold
    assert any(h.similarity < 0.3 for h in r.relevant)


def test_off_topic_question_has_no_relevant_hits(tmp_path):
    r = Retriever(EMB, _store(tmp_path), "v1", top_k=5, threshold=0.3).retrieve("capital of france poem")
    assert not r.sufficient and r.top_similarity < 0.3


def test_loan_type_filter_keeps_all_and_matching_sections_only(tmp_path):
    store = _store(tmp_path)
    r = Retriever(EMB, store, "v1", top_k=10, threshold=0.0).retrieve("minimum credit score", loan_type="FHA")
    sections = {h.section for h in r.hits}
    assert "FHA loans" in sections and "VA loans" not in sections
    assert "Timeline" in sections  # tagged ALL, so always eligible
    unfiltered = Retriever(EMB, store, "v1", top_k=10, threshold=0.0).retrieve("minimum credit score")
    assert {"FHA loans", "VA loans"} <= {h.section for h in unfiltered.hits}


def test_only_chunks_from_the_configured_version_and_model_are_searched(tmp_path):
    store = _store(tmp_path)
    assert Retriever(EMB, store, "v2", threshold=0.0).retrieve("timeline").hits == ()
    other_model = FakeEmbedder(dimensions=512, model="other-model")
    assert Retriever(other_model, store, "v1", threshold=0.0).retrieve("timeline").hits == ()
