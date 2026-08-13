"""Covers each format extract.py supports, plus the shape that matters
most for this feature: an image-only PDF export (the reference
world-championship portfolio this feature is styled on is exactly this --
an 85-page PDF with zero extractable text), which must fall back to
rasterizing pages rather than silently returning nothing."""
import io

from docx import Document
from PIL import Image

import config
from portfolio.extract import extract_all
from portfolio.ingest import IngestedFile


def _build_pdf(with_text: bool) -> bytes:
    """A minimal, spec-valid single-page PDF built by hand (no PDF-writing
    dependency needed for tests) -- with a real text content stream, or
    with no /Contents at all (a genuinely blank page, still fully
    renderable by pdfium) to exercise the image-only fallback path."""
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>"]
    if with_text:
        objs.append(
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R>>>>>>"
        )
        stream = b"BT /F1 24 Tf 10 100 Td (Hello Team) Tj ET"
        objs.append(b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream")
        objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    else:
        objs.append(b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + body + b"endobj\n"
    xref_offset = len(out)
    n = len(objs) + 1
    out += f"xref\n0 {n}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n<</Size " + str(n).encode() + b"/Root 1 0 R>>\n"
    out += b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF"
    return bytes(out)


def _png_bytes(color=(200, 30, 30), size=(40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_pdf_with_real_text_extracts_text_not_images():
    file = IngestedFile(filename="notes.pdf", extension="pdf", data=_build_pdf(with_text=True))
    result = extract_all([file])
    assert result.texts
    assert "Hello Team" in result.texts[0].text
    assert not result.images


def test_image_only_pdf_falls_back_to_rendered_page_images():
    file = IngestedFile(filename="roboctopi.pdf", extension="pdf", data=_build_pdf(with_text=False))
    result = extract_all([file])
    assert not result.texts
    assert len(result.images) == 1
    assert result.images[0].source == "pdf_page"
    assert any("image-only" in w for w in result.warnings)


def test_pdf_page_cap_is_respected(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_MAX_PDF_RENDER_PAGES", 1)
    file = IngestedFile(filename="big.pdf", extension="pdf", data=_build_pdf(with_text=False))
    result = extract_all([file])
    assert len(result.images) <= 1


def test_docx_extracts_paragraph_text():
    file = IngestedFile(filename="last_year.docx", extension="docx", data=_docx_bytes(["Season summary", "We won Think."]))
    result = extract_all([file])
    assert "Season summary" in result.texts[0].text
    assert "We won Think." in result.texts[0].text


def test_markdown_is_decoded_as_utf8():
    file = IngestedFile(filename="notes.md", extension="md", data="# Notes\n– iterate fast".encode("utf-8"))
    result = extract_all([file])
    assert "iterate fast" in result.texts[0].text


def test_txt_decode_never_raises_on_bad_bytes():
    file = IngestedFile(filename="weird.txt", extension="txt", data=b"\xff\xfe not quite utf-8 \x00")
    result = extract_all([file])
    # Must not raise -- errors="replace" guarantees a result, even if noisy.
    assert isinstance(result.texts[0].text, str)


def test_image_upload_is_normalized_and_returned_as_image():
    file = IngestedFile(filename="cad_render.png", extension="png", data=_png_bytes())
    result = extract_all([file])
    assert not result.texts
    assert result.images[0].source == "upload"
    assert result.images[0].image.mode == "RGB"


def test_oversized_image_is_downscaled_to_max_edge(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_IMAGE_MAX_EDGE_PX", 100)
    file = IngestedFile(filename="huge.png", extension="png", data=_png_bytes(size=(500, 300)))
    result = extract_all([file])
    img = result.images[0].image
    assert max(img.size) <= 100


def test_per_file_char_cap_truncates_long_text(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_MAX_EXTRACTED_CHARS_PER_FILE", 20)
    file = IngestedFile(filename="notes.md", extension="md", data=(b"x" * 500))
    result = extract_all([file])
    assert len(result.texts[0].text) <= 20


def test_total_char_cap_is_enforced_across_files(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_MAX_EXTRACTED_CHARS_TOTAL", 30)
    monkeypatch.setattr(config, "PORTFOLIO_MAX_EXTRACTED_CHARS_PER_FILE", 1000)
    files = [
        IngestedFile(filename=f"n{i}.md", extension="md", data=b"x" * 50)
        for i in range(5)
    ]
    result = extract_all(files)
    total = sum(len(t.text) for t in result.texts)
    assert total <= 30


def test_vision_image_count_is_capped_across_files(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_MAX_VISION_IMAGES", 2)
    files = [IngestedFile(filename=f"p{i}.png", extension="png", data=_png_bytes()) for i in range(5)]
    result = extract_all(files)
    assert len(result.images) == 2
    assert any("first 2 images" in w for w in result.warnings)


def test_corrupt_file_is_reported_not_raised():
    file = IngestedFile(filename="broken.pdf", extension="pdf", data=b"not a real pdf at all")
    result = extract_all([file])
    assert not result.texts
    assert not result.images
    assert any("broken.pdf" in w for w in result.warnings)


def test_unsupported_extension_reaching_extract_is_skipped_gracefully():
    file = IngestedFile(filename="weird.xyz", extension="xyz", data=b"data")
    result = extract_all([file])
    assert not result.texts
    assert not result.images
    assert result.warnings
