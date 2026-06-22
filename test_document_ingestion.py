from __future__ import annotations

import base64
import io
import unittest
from pathlib import Path

from docx import Document

from document_ingestion import DocumentIngestionError, ingest_document, ingest_document_payload


def build_docx_bytes(text: str, pages: int | None = None) -> bytes:
    del pages
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


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
        self.assertEqual(result.metadata["page_count"], None)

    def test_ingest_pdf_document(self):
        sample_pdf = Path(__file__).with_name("Product Requirement Document.pdf")
        result = ingest_document(filename=sample_pdf.name, content_bytes=sample_pdf.read_bytes())
        self.assertIn("Product Requirement Document", result.text)
        self.assertEqual(result.metadata["extension"], ".pdf")
        self.assertEqual(result.metadata["page_count"], 4)

    def test_invalid_docx_raises_structured_error(self):
        with self.assertRaises(DocumentIngestionError) as error:
            ingest_document(filename="prd.docx", content_bytes=b"not-a-docx")
        self.assertEqual(error.exception.code, "corrupted_document")

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
