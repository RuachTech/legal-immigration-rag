"""Property tests for Summary-Augmented Chunking (Property 5, Req 2.3)."""

import pytest
from hypothesis import given, strategies as st

from data_pipeline.processing.summary_augmented_chunker import (
    SummaryAugmentedChunker,
    DocumentInfo,
    DocumentSummarizer,
    RecursiveCharacterTextSplitter,
)


class StubSummarizer(DocumentSummarizer):
    """Deterministic summarizer for property tests."""

    def summarize(self, text: str, doc_title: str) -> str:  # pragma: no cover - simple stub
        return f"SUMMARY:{doc_title}"


def paragraph_strategy() -> st.SearchStrategy[str]:
    """Paragraphs with whitespace to trigger splitting."""
    alphabet = st.characters(whitelist_categories=["Ll", "Lu", "Nd", "Zs"], min_codepoint=32)
    return st.text(alphabet=alphabet, min_size=5, max_size=80)


@pytest.mark.property
@given(
    paragraphs=st.lists(paragraph_strategy(), min_size=2, max_size=5),
    title=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd"]))
)
def test_summary_augmented_chunking_prepends_summary(paragraphs, title):
    """Every chunk must carry the document summary prefix (SAC invariant)."""
    text = "\n\n".join(paragraphs)
    safe_title = title.strip() or "Doc"
    doc_info = DocumentInfo(title=safe_title, url="https://example.com/doc")

    chunker = SummaryAugmentedChunker(
        splitter=RecursiveCharacterTextSplitter(max_chunk_size=80, overlap=0),
        summarizer=StubSummarizer(),
    )

    chunks = chunker.chunk_document(text, doc_info)

    assert len(chunks) >= 1
    summaries = {chunk["summary"] for chunk in chunks}
    assert summaries == {f"SUMMARY:{safe_title}"}

    for chunk in chunks:
        assert chunk["augmented_content"].startswith(chunk["summary"])
        assert chunk["raw_content"] in chunk["augmented_content"]
        assert chunk["metadata"]["source"] == safe_title
        assert chunk["metadata"]["url"] == "https://example.com/doc"
        assert chunk["metadata"]["chunk_number"] >= 1
