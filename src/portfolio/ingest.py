"""Validates and reads uploaded attachments before any content parsing.

This is the bot's first feature that accepts file uploads, so every check
here runs as early as possible, before the more expensive parsing in
`extract.py`: file count and per-file size are checked against Discord's
own reported `attachment.size` *before* any bytes are read, then the
actual downloaded bytes' magic-byte signature is checked against what the
extension claims to be -- `attachment.content_type` and the filename are
both client-supplied and never trusted on their own (see docs/security.md).

Takes anything with `.filename: str`, `.size: int`, and an async
`.read() -> bytes` -- `discord.Attachment`'s shape -- so tests can pass a
plain fake without importing discord.py.
"""
import re
from dataclasses import dataclass

import config

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._ -]")

# Extension -> tuple of valid leading byte signatures. An empty tuple means
# "no reliable magic bytes for this format" (plain text) -- the extension
# is the only signal available, which is fine since these formats have no
# capacity to smuggle executable content through this pipeline (extract.py
# only ever decodes them as text).
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),
    "gif": (b"GIF87a", b"GIF89a"),
    "docx": (b"PK\x03\x04",),
    "md": (),
    "txt": (),
}

ALLOWED_EXTENSIONS = frozenset(_MAGIC_BYTES)
IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "webp", "gif"})


class IngestError(Exception):
    """A rejected upload. The message is written to be shown to the user
    directly -- it never includes exception text, a stack trace, or
    anything beyond the filename and a fixed reason (see docs/security.md
    on not leaking internal error detail)."""


@dataclass(frozen=True)
class IngestedFile:
    filename: str
    extension: str
    data: bytes


def _extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _sanitize_filename(filename: str) -> str:
    name = _FILENAME_SAFE_RE.sub("_", filename.strip())
    name = re.sub(r"\.\.+", "_", name)  # collapse ".."-style traversal lookalikes
    return name[:100] or "upload"


def _matches_magic_bytes(extension: str, data: bytes) -> bool:
    signatures = _MAGIC_BYTES.get(extension, ())
    if not signatures:
        return True
    if not any(data.startswith(sig) for sig in signatures):
        return False
    if extension == "webp":
        return data[8:12] == b"WEBP"
    return True


def _mb(n_bytes: int) -> float:
    return n_bytes / (1024 * 1024)


async def validate_and_read(
    attachments,
    *,
    max_files: "int | None" = None,
    max_file_mb: "float | None" = None,
    max_total_mb: "float | None" = None,
) -> list[IngestedFile]:
    max_files = max_files if max_files is not None else config.PORTFOLIO_MAX_FILES
    max_file_mb = max_file_mb if max_file_mb is not None else config.PORTFOLIO_MAX_FILE_MB
    max_total_mb = max_total_mb if max_total_mb is not None else config.PORTFOLIO_MAX_TOTAL_MB

    if len(attachments) > max_files:
        raise IngestError(f"Too many files attached -- the limit is {max_files}.")

    declared_total = 0
    for att in attachments:
        extension = _extension_of(att.filename)
        if extension not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(f".{e}" for e in ALLOWED_EXTENSIONS))
            raise IngestError(f"'{att.filename}' has an unsupported file type. Allowed: {allowed}.")
        if _mb(att.size) > max_file_mb:
            raise IngestError(f"'{att.filename}' is too large -- the per-file limit is {max_file_mb} MB.")
        declared_total += att.size

    if _mb(declared_total) > max_total_mb:
        raise IngestError(f"Total upload size is too large -- the limit is {max_total_mb} MB.")

    ingested = []
    for att in attachments:
        extension = _extension_of(att.filename)
        data = await att.read()
        if _mb(len(data)) > max_file_mb:
            raise IngestError(f"'{att.filename}' is too large -- the per-file limit is {max_file_mb} MB.")
        if not _matches_magic_bytes(extension, data):
            raise IngestError(f"'{att.filename}' doesn't look like a valid .{extension} file.")
        ingested.append(
            IngestedFile(filename=_sanitize_filename(att.filename), extension=extension, data=data)
        )
    return ingested
