from pathlib import Path
import sys
import tempfile
import unittest


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE_DIR))

from utils.file_utils import compute_file_hash, validate_pdf_file
from utils.formatters import clean_text, normalize_amount, normalize_date


class FormatterTests(unittest.TestCase):
    def test_clean_text_normalizes_whitespace_and_unicode_radicals(self) -> None:
        self.assertEqual(clean_text("  车⻔  \n 测试 "), "车门 测试")

    def test_normalize_amount(self) -> None:
        self.assertEqual(normalize_amount("￥1,234.50"), 1234.50)
        self.assertEqual(normalize_amount(" 88 "), 88.00)
        self.assertIsNone(normalize_amount("无金额"))

    def test_normalize_date(self) -> None:
        self.assertEqual(normalize_date("2026年5月1日"), "2026-05-01")
        self.assertEqual(normalize_date("2026/5/1"), "2026-05-01")
        self.assertEqual(normalize_date("2026-05-01"), "2026-05-01")
        self.assertEqual(normalize_date("2026-02-30"), "")


class FileUtilsTests(unittest.TestCase):
    def test_compute_file_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.pdf"
            second = Path(tmp_dir) / "second.pdf"
            third = Path(tmp_dir) / "third.pdf"
            first.write_bytes(b"%PDF-same")
            second.write_bytes(b"%PDF-same")
            third.write_bytes(b"%PDF-different")

            self.assertEqual(compute_file_hash(first), compute_file_hash(second))
            self.assertNotEqual(compute_file_hash(first), compute_file_hash(third))

    def test_validate_pdf_file_checks_extension_size_and_magic_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            valid = Path(tmp_dir) / "valid.PDF"
            valid.write_bytes(b"%PDF-1.7\n")
            empty = Path(tmp_dir) / "empty.pdf"
            empty.write_bytes(b"")
            fake = Path(tmp_dir) / "fake.pdf"
            fake.write_bytes(b"not a pdf")
            txt = Path(tmp_dir) / "invoice.txt"
            txt.write_bytes(b"%PDF-1.7\n")

            self.assertEqual(validate_pdf_file(valid), (True, ""))
            self.assertFalse(validate_pdf_file(empty)[0])
            self.assertIn("为空", validate_pdf_file(empty)[1])
            self.assertFalse(validate_pdf_file(fake)[0])
            self.assertIn("文件头", validate_pdf_file(fake)[1])
            self.assertFalse(validate_pdf_file(txt)[0])
            self.assertIn("不是 PDF", validate_pdf_file(txt)[1])


if __name__ == "__main__":
    unittest.main()
