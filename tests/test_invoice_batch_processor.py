from pathlib import Path
import sys
import tempfile
import unittest


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE_DIR))

from parsers.pdf_text_extractor import TextExtractionResult
from services.invoice_service import InvoiceBatchProcessor


def invoice_text(number: str, amount: str = "100.00", invoice_date: str = "2026-05-01") -> str:
    return f"""增值税电子普通发票
发票号码: {number}
开票日期: {invoice_date}
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

    def test_duplicate_invoice_number_conflicts_are_high_risk(self) -> None:
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
            self.assertTrue(records[0].duplicate_invoice_conflict)
            self.assertTrue(records[1].duplicate_invoice_conflict)
            self.assertIn("高风险重复发票", records[0].remarks)
            self.assertIn("高风险重复发票", records[1].remarks)

    def test_same_invoice_number_with_matching_fields_is_regular_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.pdf"
            second = Path(tmp_dir) / "second.pdf"
            first.write_bytes(b"%PDF-one")
            second.write_bytes(b"%PDF-two")

            processor = InvoiceBatchProcessor(enable_ocr=False)

            def fake_extract(path: Path) -> TextExtractionResult:
                return TextExtractionResult(text=invoice_text("12345678901234567890"), method="test")

            processor.extractor.extract = fake_extract  # type: ignore[method-assign]

            records = processor.process_files([first, second])

            self.assertEqual(len(records), 2)
            self.assertTrue(records[0].duplicate_invoice)
            self.assertTrue(records[1].duplicate_invoice)
            self.assertFalse(records[0].duplicate_invoice_conflict)
            self.assertFalse(records[1].duplicate_invoice_conflict)
            self.assertIn("疑似重复发票", records[0].remarks)
            self.assertIn("疑似重复发票", records[1].remarks)

    def test_invalid_amount_marks_record_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invoice = Path(tmp_dir) / "invoice.pdf"
            invoice.write_bytes(b"%PDF-one")

            processor = InvoiceBatchProcessor(enable_ocr=False)
            processor.extractor.extract = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text=invoice_text("12345678901234567890", "0.00"),
                method="test",
            )

            records = processor.process_files([invoice])

            self.assertEqual(len(records), 1)
            self.assertFalse(records[0].parse_success)
            self.assertIn("金额异常", records[0].remarks)

    def test_ocr_metadata_and_low_confidence_review_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invoice = Path(tmp_dir) / "invoice.pdf"
            invoice.write_bytes(b"%PDF-one")

            processor = InvoiceBatchProcessor(enable_ocr=True, ocr_confidence_threshold=0.75)
            processor.extractor.extract = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text=invoice_text("12345678901234567890"),
                method="OCR:fake",
                ocr_used=True,
                ocr_confidence=0.60,
                ocr_engine="fake",
            )

            records = processor.process_files([invoice])

            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].parse_success)
            self.assertTrue(records[0].ocr_used)
            self.assertEqual(records[0].ocr_confidence, 0.60)
            self.assertIn("已使用 OCR（fake）", records[0].remarks)
            self.assertIn("OCR 置信度偏低", records[0].remarks)

    def test_far_future_invoice_date_marks_record_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invoice = Path(tmp_dir) / "invoice.pdf"
            invoice.write_bytes(b"%PDF-one")

            processor = InvoiceBatchProcessor(enable_ocr=False)
            processor.extractor.extract = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text=invoice_text("12345678901234567890", invoice_date="2099-01-01"),
                method="test",
            )

            records = processor.process_files([invoice])

            self.assertEqual(len(records), 1)
            self.assertFalse(records[0].parse_success)
            self.assertIn("开票日期异常", records[0].remarks)

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

    def test_automatic_ocr_audit_fills_missing_core_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invoice = Path(tmp_dir) / "invoice.pdf"
            invoice.write_bytes(b"%PDF-one")

            processor = InvoiceBatchProcessor(enable_ocr=True)
            processor.extractor.extract = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text="""增值税电子普通发票
发票号码: 12345678901234567890
开票日期: 2026-05-01
购买方信息 名称: 北京示例科技有限公司
销售方信息 名称: 上海样例服务有限公司
""",
                method="PyMuPDF",
            )
            processor.extractor.extract_ocr = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text=invoice_text("12345678901234567890", "100.00"),
                method="OCR:fake",
                ocr_used=True,
                ocr_confidence=0.96,
                ocr_engine="fake",
            )

            records = processor.process_files([invoice])

            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].parse_success)
            self.assertEqual(records[0].total_amount, 100.0)
            self.assertTrue(records[0].ocr_used)
            self.assertEqual(records[0].ocr_confidence, 0.96)
            self.assertIn("OCR自动补全金额", records[0].remarks)
            self.assertNotIn("缺少金额", records[0].remarks)

    def test_automatic_ocr_audit_marks_core_conflict_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invoice = Path(tmp_dir) / "invoice.pdf"
            invoice.write_bytes(b"%PDF-one")

            processor = InvoiceBatchProcessor(enable_ocr=True)
            processor.extractor.extract = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text="""增值税电子普通发票
发票号码: 12345678901234567890
开票日期: 2026-05-01
购 销 买 名称: 北京示例科技有限公司 售 名称: 上海样例服务有限公司 方 方 信
价税合计（小写） ￥100.00
""",
                method="PyMuPDF",
            )
            processor.extractor.extract_ocr = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text=invoice_text("12345678901234567899", "100.00"),
                method="OCR:fake",
                ocr_used=True,
                ocr_confidence=0.95,
                ocr_engine="fake",
            )

            records = processor.process_files([invoice])

            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].parse_success)
            self.assertEqual(records[0].invoice_number, "12345678901234567890")
            self.assertTrue(records[0].ocr_used)
            self.assertIn("高风险：PDF文本/OCR发票号码不一致", records[0].remarks)

    def test_automatic_ocr_audit_corrects_suspicious_party_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invoice = Path(tmp_dir) / "invoice.pdf"
            invoice.write_bytes(b"%PDF-one")

            processor = InvoiceBatchProcessor(enable_ocr=True)
            processor.extractor.extract = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text="""增值税电子普通发票
发票号码: 12345678901234567890
开票日期: 2026-05-01
购买方信息 名称: 北京示例科技有限公司
销售方信息 名称: 上海样例服务有限公司 方 方 信 信息统一社会信用代码/纳税人识别号:91310115MA0000000Y
价税合计（小写） ￥100.00
""",
                method="PyMuPDF",
            )
            processor.extractor.extract_ocr = lambda path: TextExtractionResult(  # type: ignore[method-assign]
                text=invoice_text("12345678901234567890", "100.00"),
                method="OCR:fake",
                ocr_used=True,
                ocr_confidence=0.95,
                ocr_engine="fake",
            )

            records = processor.process_files([invoice])

            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].parse_success)
            self.assertEqual(records[0].seller_name, "上海样例服务有限公司")
            self.assertIn("OCR自动修正销售方名称", records[0].remarks)


if __name__ == "__main__":
    unittest.main()
