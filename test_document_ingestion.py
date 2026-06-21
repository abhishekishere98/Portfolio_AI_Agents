from __future__ import annotations

import base64
import io
import unittest
import zipfile
import zlib

from document_ingestion import DocumentIngestionError, ingest_document, ingest_document_payload


def build_docx_bytes(text: str, pages: int | None = None) -> bytes:
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body><w:p><w:r><w:t>"
        + text
        + "</w:t></w:r></w:p></w:body></w:document>"
    )
    app_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\">"
        + (f"<Pages>{pages}</Pages>" if pages is not None else "")
        + "</Properties>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("docProps/app.xml", app_xml)
    return buffer.getvalue()


def build_pdf_bytes(text: str) -> bytes:
    stream = f"BT ({text}) Tj ET"
    pdf = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
        f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n"
        "xref\n0 5\n0000000000 65535 f \n"
        "trailer << /Root 1 0 R /Size 5 >>\nstartxref\n0\n%%EOF\n"
    )
    return pdf.encode("latin-1")


def build_compressed_pdf_bytes(text: str) -> bytes:
    stream = f"BT ({text}) Tj ET".encode("latin-1")
    compressed = zlib.compress(stream)
    pdf = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
        f"4 0 obj << /Length {len(compressed)} /Filter /FlateDecode >> stream\n"
    ).encode("latin-1") + compressed + b"\nendstream endobj\n" + (
        "xref\n0 5\n0000000000 65535 f \n"
        "trailer << /Root 1 0 R /Size 5 >>\nstartxref\n0\n%%EOF\n"
    ).encode("latin-1")
    return pdf


class DocumentIngestionTests(unittest.TestCase):
    def test_ingest_txt_document(self):
        result = ingest_document(filename="prd.txt", content_bytes=b"Hello\n\nWorld")
        self.assertEqual(result.text, "Hello\n\nWorld")
        self.assertEqual(result.metadata["extension"], ".txt")
        self.assertEqual(result.metadata["word_count"], 2)
        self.assertEqual(result.metadata["page_count"], None)

    def test_ingest_markdown_document(self):
        result = ingest_document(filename="prd.md", content_bytes=b"# PRD\n- Item")
        self.assertEqual(result.metadata["extension"], ".md")
        self.assertGreater(result.metadata["character_count"], 0)

    def test_ingest_docx_document(self):
        result = ingest_document(filename="prd.docx", content_bytes=build_docx_bytes("DOCX content", pages=3))
        self.assertIn("DOCX content", result.text)
        self.assertEqual(result.metadata["extension"], ".docx")
        self.assertEqual(result.metadata["page_count"], 3)

    def test_ingest_pdf_document(self):
        result = ingest_document(filename="prd.pdf", content_bytes=build_pdf_bytes("PDF content"))
        self.assertIn("PDF content", result.text)
        self.assertEqual(result.metadata["extension"], ".pdf")
        self.assertEqual(result.metadata["page_count"], 1)

    def test_ingest_compressed_pdf_document(self):
        result = ingest_document(filename="prd.pdf", content_bytes=build_compressed_pdf_bytes("Compressed PDF"))
        self.assertIn("Compressed PDF", result.text)
        self.assertEqual(result.metadata["extension"], ".pdf")

    def test_unsupported_file_type_raises_structured_error(self):
        with self.assertRaises(DocumentIngestionError) as error:
            ingest_document(filename="prd.csv", content_bytes=b"a,b,c")
        self.assertEqual(error.exception.code, "unsupported_file_type")

    def test_empty_document_raises_structured_error(self):
        with self.assertRaises(DocumentIngestionError) as error:
            ingest_document(filename="prd.txt", content_bytes=b"  \n\t  ")
        self.assertEqual(error.exception.code, "empty_document")

    def test_payload_base64_decode_error(self):
        with self.assertRaises(DocumentIngestionError) as error:
            ingest_document_payload(
                {
                    "uploaded_file": {
                        "filename": "prd.txt",
                        "content_base64": "not-base64$$$",
                    }
                }
            )
        self.assertEqual(error.exception.code, "corrupted_document")

    def test_payload_ingestion_success(self):
        raw = b"This is PRD text"
        payload = {
            "uploaded_file": {
                "filename": "prd.txt",
                "content_base64": base64.b64encode(raw).decode("ascii"),
            }
        }
        result = ingest_document_payload(payload)
        self.assertEqual(result.text, "This is PRD text")

    def test_payload_data_url_base64_success(self):
        raw = b"This is PRD text"
        payload = {
            "uploaded_file": {
                "filename": "prd.txt",
                "content_base64": f"data:text/plain;base64,{base64.b64encode(raw).decode('ascii')}",
            }
        }
        result = ingest_document_payload(payload)
        self.assertEqual(result.text, "This is PRD text")


if __name__ == "__main__":
    unittest.main()
