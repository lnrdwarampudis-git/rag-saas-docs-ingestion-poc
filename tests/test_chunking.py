from app.rag.chunking import ChunkingConfig, chunk_text


def test_chunking_creates_overlapping_chunks_with_metadata() -> None:
    text = " ".join(f"token{i}" for i in range(240))
    chunks = chunk_text(
        text,
        config=ChunkingConfig(target_tokens=100, overlap_tokens=20, min_chunk_tokens=1),
        base_metadata={"tenant_id": "tenant-1", "visibility": "role", "allowed_role_names": ["analyst"]},
    )

    assert len(chunks) == 3
    assert chunks[0].token_count == 100
    assert chunks[1].text.startswith("token80 token81")
    assert chunks[0].metadata["tenant_id"] == "tenant-1"
    assert chunks[0].metadata["allowed_role_names"] == ["analyst"]


def test_chunking_empty_text_returns_no_chunks() -> None:
    assert chunk_text(" \n\n ") == []


def test_chunking_rejects_invalid_overlap() -> None:
    try:
        ChunkingConfig(target_tokens=100, overlap_tokens=100)
    except ValueError as exc:
        assert "overlap_tokens" in str(exc)
    else:
        raise AssertionError("Expected invalid overlap to raise ValueError")
