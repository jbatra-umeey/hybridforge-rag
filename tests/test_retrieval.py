import pytest

from hybridforge.models import Hit
from hybridforge.retrieval import chunk_text, cosine, rrf, select_context


def hit(id, start=0, end=100):
    return Hit(id, "doc", 1, "Title", "source", "x" * (end - start), start, end)


def test_chunks_preserve_text_and_cover_every_character():
    text = "Alpha beta gamma.\n" * 1000
    chunks = chunk_text(text)
    covered = set()
    for start, end, body in chunks:
        assert body == text[start:end]
        assert end - start <= 1200
        covered.update(range(start, end))
    assert len(covered) == len(text)


def test_chunker_empty_and_overlap_validation():
    assert chunk_text("") == []
    with pytest.raises(ValueError):
        chunk_text("x", 10, 10)


def test_rrf_accumulates_ranks_without_mutating_inputs():
    a, b, c = hit("a"), hit("b"), hit("c")
    result = rrf([a, b], [b, c])
    assert result[0].chunk_id == "b"
    assert result[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert result[0].ranks == {"lexical": 2, "dense": 1}
    assert a.score == 0


def test_rrf_duplicate_not_double_counted():
    a = hit("a")
    assert rrf([a, a], [])[0].score == pytest.approx(1 / 61)


def test_context_dedup_and_budget():
    chosen = select_context([hit("a"), hit("b", 20, 100), hit("c", 200, 300)], 5, 150)
    assert [h.chunk_id for h in chosen] == ["a"]


def test_cosine_dimension_mismatch():
    with pytest.raises(ValueError):
        cosine([1, 0], [1])
    assert cosine([0, 0], [1, 0]) == 0
