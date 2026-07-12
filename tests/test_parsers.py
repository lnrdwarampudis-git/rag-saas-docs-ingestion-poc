from pathlib import Path
from zipfile import ZipFile

import pytest

from app.rag.parsers import extract_document_text


def test_plain_text_extraction(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("Quarterly revenue policy\nOnly finance can read this.", encoding="utf-8")

    result = extract_document_text(source)

    assert "Quarterly revenue policy" in result.text
    assert result.ocr_used is False


def test_xlsx_extraction(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")

    source = tmp_path / "sample.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Policies"
    worksheet.append(["Topic", "Rule"])
    worksheet.append(["Knowledge representation", "Use authorized context"])
    workbook.save(source)

    result = extract_document_text(source)

    assert "Sheet: Policies" in result.text
    assert "Knowledge representation | Use authorized context" in result.text


def test_pptx_extraction(tmp_path: Path) -> None:
    source = tmp_path / "sample.pptx"
    slide_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:cSld>
        <p:spTree>
          <p:sp><p:txBody><a:p><a:r><a:t>RAG architecture</a:t></a:r></a:p></p:txBody></p:sp>
          <p:sp><p:txBody><a:p><a:r><a:t>Session management</a:t></a:r></a:p></p:txBody></p:sp>
        </p:spTree>
      </p:cSld>
    </p:sld>
    """
    with ZipFile(source, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", slide_xml)

    result = extract_document_text(source)

    assert "Slide 1: RAG architecture Session management" in result.text
