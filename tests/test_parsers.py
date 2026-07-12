from pathlib import Path

from app.rag.parsers import extract_document_text


def test_plain_text_extraction(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("Quarterly revenue policy\nOnly finance can read this.", encoding="utf-8")

    result = extract_document_text(source)

    assert "Quarterly revenue policy" in result.text
    assert result.ocr_used is False
