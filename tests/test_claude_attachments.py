import base64

from discord_claude.cogs.claude.attachments import (
    build_attachment_content_block,
    infer_attachment_content_type,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"payload"
GIF_BYTES = b"GIF89a" + b"payload"
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8 payload"
PDF_BYTES = b"%PDF-1.7\n%payload"


class TestInferAttachmentContentType:
    def test_png_magic_bytes_override_declared_type(self):
        """PNG bytes win even when Discord lies and says image/jpeg."""
        assert infer_attachment_content_type("image/jpeg", PNG_BYTES, "IMG_3950.png") == "image/png"

    def test_jpeg_magic_bytes(self):
        assert infer_attachment_content_type("application/octet-stream", JPEG_BYTES) == "image/jpeg"

    def test_gif_magic_bytes(self):
        assert infer_attachment_content_type("image/png", GIF_BYTES) == "image/gif"

    def test_webp_magic_bytes(self):
        assert infer_attachment_content_type("image/jpeg", WEBP_BYTES) == "image/webp"

    def test_pdf_magic_bytes(self):
        assert infer_attachment_content_type("application/pdf", PDF_BYTES) == "application/pdf"

    def test_falls_back_to_declared_type_for_unsniffable_bytes(self):
        """Text and other non-sniffed types keep the declared content type."""
        assert infer_attachment_content_type("text/plain", b"just some text") == "text/plain"

    def test_strips_charset_parameter(self):
        assert (
            infer_attachment_content_type("text/markdown; charset=utf-8", b"# hi")
            == "text/markdown"
        )

    def test_falls_back_to_filename_when_content_type_blank(self):
        result = infer_attachment_content_type("", b"unknown bytes", "notes.txt")
        assert result == "text/plain"

    def test_returns_empty_string_when_nothing_resolves(self):
        assert infer_attachment_content_type("", b"unknown bytes", None) == ""


class TestBuildAttachmentContentBlock:
    def test_png_bytes_win_over_wrong_discord_content_type(self):
        """Regression: Discord reported IMG_3950.png as image/jpeg; bytes were PNG.

        The PNG bytes must drive the Anthropic media_type, or the request 400s.
        """
        block = build_attachment_content_block("image/jpeg", PNG_BYTES, "IMG_3950.png")
        assert block is not None
        assert block["type"] == "image"
        assert block["source"]["media_type"] == "image/png"
        assert base64.b64decode(block["source"]["data"]) == PNG_BYTES

    def test_correctly_labeled_jpeg_is_unchanged(self):
        block = build_attachment_content_block("image/jpeg", JPEG_BYTES, "photo.jpg")
        assert block is not None
        assert block["source"]["media_type"] == "image/jpeg"

    def test_pdf_routes_to_document_block(self):
        block = build_attachment_content_block("application/pdf", PDF_BYTES, "report.pdf")
        assert block is not None
        assert block["type"] == "document"
        assert block["source"]["media_type"] == "application/pdf"
        assert block["title"] == "report.pdf"

    def test_mislabeled_image_as_octet_stream_still_routes_to_image(self):
        """A real PNG sent as application/octet-stream is still an image."""
        block = build_attachment_content_block("application/octet-stream", PNG_BYTES, "blob")
        assert block is not None
        assert block["type"] == "image"
        assert block["source"]["media_type"] == "image/png"

    def test_text_attachment_routes_to_text_document(self):
        block = build_attachment_content_block("text/plain", b"hello world", "notes.txt")
        assert block is not None
        assert block["type"] == "document"
        assert block["source"]["type"] == "text"
        assert block["source"]["data"] == "hello world"

    def test_unsupported_type_returns_none(self):
        block = build_attachment_content_block("application/zip", b"PK\x03\x04zipdata", "a.zip")
        assert block is None
