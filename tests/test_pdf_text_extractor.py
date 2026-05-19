from pathlib import Path
import sys
import unittest


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE_DIR))

from parsers.pdf_text_extractor import PDFTextExtractor
from services.ocr_service import OCRResult


class FakeOCRService:
    def recognize(self, image_array):
        return OCRResult(text="", confidence=None, engine_name="fake")

    def score_result(self, result):
        return len(result.text), result.confidence or 0.0


class PDFTextExtractorTests(unittest.TestCase):
    def test_default_ocr_page_limit_supports_multi_page_invoices(self) -> None:
        extractor = PDFTextExtractor(FakeOCRService(), enable_ocr=True)

        self.assertEqual(extractor.max_ocr_pages, 10)

    def test_pymupdf_text_shortcuts_fallbacks(self) -> None:
        extractor = PDFTextExtractor(FakeOCRService(), enable_ocr=True)
        extractor._extract_with_pymupdf = lambda path: "发票号码 12345678901234567890 金额 100 日期 2026-05-01"  # type: ignore[method-assign]
        extractor._extract_with_pdfplumber = lambda path: self.fail("pdfplumber should not be called")  # type: ignore[method-assign]
        extractor._extract_with_ocr = lambda path: self.fail("ocr should not be called")  # type: ignore[method-assign]

        result = extractor.extract(Path("dummy.pdf"))

        self.assertEqual(result.method, "PyMuPDF")
        self.assertFalse(result.ocr_used)

    def test_pdfplumber_fallback_when_pymupdf_text_is_not_enough(self) -> None:
        extractor = PDFTextExtractor(FakeOCRService(), enable_ocr=True)
        extractor._extract_with_pymupdf = lambda path: "短"  # type: ignore[method-assign]
        extractor._extract_with_pdfplumber = lambda path: "发票号码 12345678901234567890 金额 100 日期 2026-05-01"  # type: ignore[method-assign]
        extractor._extract_with_ocr = lambda path: self.fail("ocr should not be called")  # type: ignore[method-assign]

        result = extractor.extract(Path("dummy.pdf"))

        self.assertEqual(result.method, "pdfplumber")

    def test_ocr_disabled_returns_clear_error(self) -> None:
        extractor = PDFTextExtractor(FakeOCRService(), enable_ocr=False)
        extractor._extract_with_pymupdf = lambda path: ""  # type: ignore[method-assign]
        extractor._extract_with_pdfplumber = lambda path: ""  # type: ignore[method-assign]

        result = extractor.extract(Path("dummy.pdf"))

        self.assertEqual(result.method, "none")
        self.assertIn("未启用 OCR", result.errors[0])

    def test_ocr_exception_is_reported_without_raw_exception_text(self) -> None:
        extractor = PDFTextExtractor(FakeOCRService(), enable_ocr=True)
        extractor._extract_with_pymupdf = lambda path: ""  # type: ignore[method-assign]
        extractor._extract_with_pdfplumber = lambda path: ""  # type: ignore[method-assign]
        extractor._extract_with_ocr = lambda path: (_ for _ in ()).throw(RuntimeError("secret path"))  # type: ignore[method-assign]

        result = extractor.extract(Path("dummy.pdf"))

        self.assertEqual(result.method, "failed")
        self.assertEqual(result.errors, ["OCR 识别失败"])


if __name__ == "__main__":
    unittest.main()
