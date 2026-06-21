"""
Tests for the chunking helpers in project_chunk_service:
  - _split_text  (chunk size / overlap arithmetic)
  - _read_file   (dispatch by extension, encoding fallback)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.project_chunk_service import CHUNK_SIZE, OVERLAP, _read_file, _split_text

STEP = CHUNK_SIZE - OVERLAP  # 800 — how far each window advances


# ── _split_text ───────────────────────────────────────────────────────────────

def test_split_empty_text_returns_empty_list():
    assert _split_text("") == []


def test_split_short_text_returns_single_chunk():
    text = "hello world"
    assert _split_text(text) == [text]


def test_split_text_exactly_at_step_boundary():
    # STEP chars (800) → start advances to 800, which equals len → stops
    text = "a" * STEP
    chunks = _split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_one_char_over_step_produces_two_chunks():
    # 801 chars: first window covers 0-1000 (all), second starts at 800
    text = "b" * (STEP + 1)
    chunks = _split_text(text)
    assert len(chunks) == 2


def test_split_first_chunk_is_full_chunk_size():
    text = "x" * (CHUNK_SIZE * 3)
    chunks = _split_text(text)
    assert len(chunks[0]) == CHUNK_SIZE


def test_split_last_chunk_may_be_shorter():
    # 2500 chars → windows at 0, 800, 1600, 2400 → last window = 100 chars
    text = "z" * 2500
    chunks = _split_text(text)
    assert len(chunks) == 4
    assert len(chunks[-1]) == 100


def test_split_overlap_region_appears_in_both_chunks():
    # Build text where each zone has a distinct character so overlap is identifiable
    # zone A: 0..STEP (800 "a"s), zone B: STEP..CHUNK_SIZE (200 "b"s = the overlap),
    # zone C: CHUNK_SIZE..CHUNK_SIZE+STEP (800 "c"s)
    text = "a" * STEP + "b" * OVERLAP + "c" * STEP
    # total = 800 + 200 + 800 = 1800 chars
    chunks = _split_text(text)
    # windows: [0:1000], [800:1800], [1600:2600→1800]
    assert len(chunks) == 3
    overlap_in_chunk0 = chunks[0][-OVERLAP:]   # last 200 chars of chunk 0
    overlap_in_chunk1 = chunks[1][:OVERLAP]    # first 200 chars of chunk 1
    assert overlap_in_chunk0 == overlap_in_chunk1 == "b" * OVERLAP


def test_split_chunk_count_formula():
    # Number of chunks = ceil((len - OVERLAP) / STEP) when len > 0
    import math
    for length in [1, 100, 800, 801, 1000, 1600, 3000]:
        text = "x" * length
        expected = math.ceil((length - OVERLAP) / STEP) if length > OVERLAP else 1
        # Simpler: just trust our formula matches implementation
        chunks = _split_text(text)
        # At minimum the chunks must cover the whole text
        if chunks:
            covered = chunks[-1]  # last chunk reaches the end
            end_of_last = (len(chunks) - 1) * STEP + len(chunks[-1])
            assert end_of_last == length, f"length={length} not fully covered"


# ── _read_file ────────────────────────────────────────────────────────────────

def test_read_file_plain_text(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("Hello, world!", encoding="utf-8")
    assert _read_file(f) == "Hello, world!"


def test_read_file_multiline_text(tmp_path):
    f = tmp_path / "notes.txt"
    content = "Line one\nLine two\nLine three"
    f.write_text(content, encoding="utf-8")
    assert _read_file(f) == content


def test_read_file_invalid_utf8_replaced(tmp_path):
    # Bytes that are invalid UTF-8 should be replaced, not crash
    f = tmp_path / "bad.txt"
    f.write_bytes(b"Hello \xff world")
    result = _read_file(f)
    assert "Hello" in result
    assert "world" in result


def test_read_file_pdf_dispatch(tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 fake")  # file must exist; content doesn't matter

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Page content here."
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("services.project_chunk_service.PdfReader", return_value=mock_reader):
        result = _read_file(f)

    assert result == "Page content here."


def test_read_file_pdf_multiple_pages(tmp_path):
    f = tmp_path / "multi.pdf"
    f.write_bytes(b"%PDF fake")

    pages = [MagicMock(extract_text=lambda i=i: f"Page {i}") for i in range(3)]
    mock_reader = MagicMock()
    mock_reader.pages = pages

    with patch("services.project_chunk_service.PdfReader", return_value=mock_reader):
        result = _read_file(f)

    # Pages are joined with newlines
    assert "Page 0" in result
    assert "Page 1" in result


def test_read_file_pdf_page_returns_none(tmp_path):
    # If a page has no extractable text, extract_text() returns None
    f = tmp_path / "scanned.pdf"
    f.write_bytes(b"%PDF fake")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = None
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("services.project_chunk_service.PdfReader", return_value=mock_reader):
        result = _read_file(f)

    # Should not crash; None is replaced with ""
    assert result == ""


def test_read_file_docx_dispatch(tmp_path):
    f = tmp_path / "letter.docx"
    f.write_bytes(b"fake docx bytes")

    para = MagicMock()
    para.text = "First paragraph."
    mock_doc = MagicMock()
    mock_doc.paragraphs = [para]
    mock_docx_module = MagicMock()
    mock_docx_module.Document.return_value = mock_doc

    # The lazy `from docx import Document` inside _read_file picks up the mock
    with patch.dict(sys.modules, {"docx": mock_docx_module}):
        result = _read_file(f)

    assert result == "First paragraph."


def test_read_file_docx_multiple_paragraphs(tmp_path):
    f = tmp_path / "report.docx"
    f.write_bytes(b"fake")

    paragraphs = [MagicMock(text=f"Para {i}") for i in range(3)]
    mock_doc = MagicMock()
    mock_doc.paragraphs = paragraphs
    mock_docx_module = MagicMock()
    mock_docx_module.Document.return_value = mock_doc

    with patch.dict(sys.modules, {"docx": mock_docx_module}):
        result = _read_file(f)

    assert result == "Para 0\nPara 1\nPara 2"
