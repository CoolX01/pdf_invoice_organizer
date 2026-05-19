from pathlib import Path
import sys
import tempfile
import unittest


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE_DIR))

from parsers.pdf_text_extractor import TextExtractionResult
from services.invoice_service import InvoiceBatchProcessor


def invoice_text(number: str, amount: str = "100.00") -> str:
    return f"""增值税电子普通发票
发票号码: {number}
开票日期: 2026-05-01
购买方信息 名称: 北京示例科技有限公司
销售方信息 名称: 上海样例服务有限公司
价税合计（小写） ￥{amount}
"""


class InvoiceBatchProcessorTests(unittest.TestCase):
    def test_duplicate_file_reuses_first_parse_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.pdf"
            second = Path(tmp_dir) / "second.pdf"
            first.write_bytes(b"%PDF-duplicate")
            second.write_bytes(b"%PDF-duplicate")

            processor = InvoiceBatchProcessor(enable_ocr=False)
            calls: list[Path] = []

            def fake_extract(path: Path) -> TextExtractionResult:
                calls.append(path)
                return TextExtractionResult(text=invoice_text("12345678901234567890"), method="test")

            processor.extractor.extract = fake_extract  # type: ignore[method-assign]

            records = processor.process_files([first, second])

            self.assertEqual(len(records), 2)
            self.assertEqual(calls, [first])
            self.assertFalse(records[0].duplicate_file)
            self.assertTrue(records[1].duplicate_file)
            self.assertFalse(records[0].duplicate_invoice)
            self.assertFalse(records[1].duplicate_invoice)
            self.assertEqual(records[1].invoice_number, records[0].invoice_number)
            self.assertIn("复用首次识别结果", records[1].remarks)

    def test_duplicate_invoice_numbers_are_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.pdf"
            second = Path(tmp_dir) / "second.pdf"
            first.write_bytes(b"%PDF-one")
            second.write_bytes(b"%PDF-two")

            processor = InvoiceBatchProcessor(enable_ocr=False)

            def fake_extract(path: Path) -> TextExtractionResult:
                amount = "100.00" if path == first else "200.00"
                return TextExtractionResult(text=invoice_text("12345678901234567890", amount), method="test")

            processor.extractor.extract = fake_extract  # type: ignore[method-assign]

            records = processor.process_files([first, second])

            self.assertEqual(len(records), 2)
            self.assertTrue(records[0].duplicate_invoice)
            self.assertTrue(records[1].duplicate_invoice)
            self.assertIn("疑似重复发票", records[0].remarks)
            self.assertIn("疑似重复发票", records[1].remarks)

    def test_empty_text_marks_record_as_failed_without_stopping_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.pdf"
            second = Path(tmp_dir) / "second.pdf"
            first.write_bytes(b"%PDF-one")
            second.write_bytes(b"%PDF-two")

            processor = InvoiceBatchProcessor(enable_ocr=False)

            def fake_extract(path: Path) -> TextExtractionResult:
                if path == first:
                    return TextExtractionResult(text="", method="test")
                return TextExtractionResult(text=invoice_text("12345678901234567890"), method="test")

            processor.extractor.extract = fake_extract  # type: ignore[method-assign]

            records = processor.process_files([first, second])

            self.assertEqual(len(records), 2)
            self.assertFalse(records[0].parse_success)
            self.assertIn("识别失败", records[0].remarks)
            self.assertTrue(records[1].parse_success)


if __name__ == "__main__":
    unittest.main()
