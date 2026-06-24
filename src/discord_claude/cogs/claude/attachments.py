import base64
import mimetypes
from typing import Any

import aiohttp
from discord import Attachment

from .client import get_http_session

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SUPPORTED_DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
}


def _sniff_attachment_media_type(data: bytes) -> str | None:
    """Detect a binary attachment's media type from its magic bytes.

    Returns ``None`` when the signature is unrecognized so the caller can fall
    back to the declared content type.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def infer_attachment_content_type(
    content_type: str | None,
    data: bytes,
    filename: str | None = None,
) -> str:
    """Resolve the most trustworthy media type for an attachment.

    Discord occasionally mislabels attachments (e.g. a PNG advertised as
    ``image/jpeg``); Anthropic then rejects the image because the declared
    ``media_type`` disagrees with the actual bytes. Trust the file's magic
    bytes first, then the Discord-provided content type, then the filename
    extension.
    """
    sniffed = _sniff_attachment_media_type(data)
    if sniffed:
        return sniffed
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized:
        return normalized
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    return ""


def build_attachment_content_block(
    content_type: str,
    data: bytes,
    filename: str | None = None,
) -> dict[str, Any] | None:
    """Build the appropriate Anthropic content block for an attachment."""
    content_type = infer_attachment_content_type(content_type, data, filename)
    if content_type in SUPPORTED_IMAGE_TYPES:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": content_type,
                "data": base64.b64encode(data).decode("utf-8"),
            },
        }
    if content_type == "application/pdf":
        block: dict[str, Any] = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(data).decode("utf-8"),
            },
            "citations": {"enabled": True},
        }
        if filename:
            block["title"] = filename
        return block
    if content_type in SUPPORTED_DOCUMENT_TYPES or (
        content_type and content_type.startswith("text/")
    ):
        try:
            text_content = data.decode("utf-8")
        except UnicodeDecodeError:
            text_content = data.decode("latin-1")

        block = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": text_content,
            },
            "citations": {"enabled": True},
        }
        if filename:
            block["title"] = filename
        return block
    return None


async def fetch_attachment_bytes(cog, attachment: Attachment) -> bytes | None:
    """Fetch raw bytes for a Discord attachment."""
    session = await get_http_session(cog)
    try:
        async with session.get(attachment.url) as response:
            if response.status == 200:
                return await response.read()
            cog.logger.warning(
                "Failed to fetch attachment %s: HTTP %s",
                attachment.url,
                response.status,
            )
    except aiohttp.ClientError as error:
        cog.logger.warning("Error fetching attachment %s: %s", attachment.url, error)
    return None


__all__ = [
    "SUPPORTED_DOCUMENT_TYPES",
    "SUPPORTED_IMAGE_TYPES",
    "build_attachment_content_block",
    "fetch_attachment_bytes",
    "infer_attachment_content_type",
]
