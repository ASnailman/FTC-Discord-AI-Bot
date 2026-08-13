import pytest

import config
from portfolio.ingest import IngestError, validate_and_read

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 20


class FakeAttachment:
    def __init__(self, filename: str, data: bytes, size: "int | None" = None):
        self.filename = filename
        self.data = data
        self.size = size if size is not None else len(data)

    async def read(self) -> bytes:
        return self.data


@pytest.mark.anyio
async def test_valid_png_is_accepted():
    files = await validate_and_read([FakeAttachment("photo.png", PNG_BYTES)])
    assert files[0].extension == "png"
    assert files[0].data == PNG_BYTES


@pytest.mark.anyio
async def test_valid_pdf_is_accepted():
    files = await validate_and_read([FakeAttachment("notes.pdf", PDF_BYTES)])
    assert files[0].extension == "pdf"


@pytest.mark.anyio
async def test_unsupported_extension_is_rejected():
    with pytest.raises(IngestError):
        await validate_and_read([FakeAttachment("payload.exe", b"MZ" + b"\x00" * 20)])


@pytest.mark.anyio
async def test_exe_renamed_to_png_extension_is_rejected_by_magic_bytes():
    with pytest.raises(IngestError):
        await validate_and_read([FakeAttachment("totally_a_photo.png", b"MZ" + b"\x00" * 20)])


@pytest.mark.anyio
async def test_html_renamed_to_pdf_extension_is_rejected_by_magic_bytes():
    with pytest.raises(IngestError):
        await validate_and_read([FakeAttachment("report.pdf", b"<html><script>evil()</script></html>")])


@pytest.mark.anyio
async def test_oversized_file_is_rejected_before_read(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_MAX_FILE_MB", 0.001)
    huge = FakeAttachment("big.png", PNG_BYTES, size=10 * 1024 * 1024)

    async def _should_not_be_called():
        raise AssertionError("read() should never be called once declared size exceeds the cap")

    huge.read = _should_not_be_called
    with pytest.raises(IngestError):
        await validate_and_read([huge], max_file_mb=0.001)


@pytest.mark.anyio
async def test_total_size_cap_is_enforced():
    files = [FakeAttachment(f"f{i}.png", PNG_BYTES, size=5 * 1024 * 1024) for i in range(3)]
    with pytest.raises(IngestError):
        await validate_and_read(files, max_total_mb=10, max_files=10)


@pytest.mark.anyio
async def test_too_many_files_is_rejected():
    files = [FakeAttachment(f"f{i}.png", PNG_BYTES) for i in range(10)]
    with pytest.raises(IngestError):
        await validate_and_read(files, max_files=6)


@pytest.mark.anyio
async def test_declared_size_lies_are_caught_after_read():
    lying = FakeAttachment("small.png", PNG_BYTES + b"\x00" * (2 * 1024 * 1024), size=1)
    with pytest.raises(IngestError):
        await validate_and_read([lying], max_file_mb=0.5)


@pytest.mark.anyio
async def test_path_traversal_filename_is_sanitized():
    files = await validate_and_read([FakeAttachment("../../etc/passwd.png", PNG_BYTES)])
    assert "/" not in files[0].filename
    assert ".." not in files[0].filename


@pytest.mark.anyio
async def test_webp_requires_webp_marker_not_just_riff():
    riff_but_not_webp = b"RIFF" + b"\x00" * 4 + b"AVI " + b"\x00" * 20
    with pytest.raises(IngestError):
        await validate_and_read([FakeAttachment("clip.webp", riff_but_not_webp)])


@pytest.mark.anyio
async def test_markdown_has_no_magic_byte_requirement():
    files = await validate_and_read([FakeAttachment("notes.md", b"# Hello team")])
    assert files[0].extension == "md"
