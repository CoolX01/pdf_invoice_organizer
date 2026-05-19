from pathlib import Path
import sys
import unittest


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE_DIR))

from models.invoice_record import InvoiceRecord
from parsers.invoice_parser import InvoiceParser


STANDARD_INVOICE_TEXT = """增值税电子普通发票
发票号码: 12345678901234567890
开票日期: 2026年05月01日
购买方信息 名称: 北京示例科技有限公司 统一社会信用代码: 91110108MA0000000X
销售方信息 名称: 上海样例服务有限公司 统一社会信用代码: 91310115MA0000000Y
*信息技术服务*软件服务 1 100.00
价税合计（小写） ￥1,234.50
"""


class InvoiceParserTests(unittest.TestCase):
    def _record(self, name: str = "示例发票.pdf") -> InvoiceRecord:
        return InvoiceRecord(file_path=Path(name), file_name=name, index=1)

    def test_parse_standard_invoice_text(self) -> None:
        record = self._record()

        InvoiceParser(invoice_title_source="invoice_type").parse(record, STANDARD_INVOICE_TEXT)

        self.assertEqual(record.invoice_number, "12345678901234567890")
        self.assertEqual(record.total_amount, 1234.50)
        self.assertEqual(record.invoice_date, "2026-05-01")
        self.assertEqual(record.buyer_name, "北京示例科技有限公司")
        self.assertEqual(record.seller_name, "上海样例服务有限公司")
        self.assertIn("*信息技术服务*软件服务", record.item_name)
        self.assertEqual(record.invoice_title, "增值税电子普通发票")
        self.assertTrue(record.parse_success)

    def test_filename_title_source_uses_file_stem(self) -> None:
        record = self._record("报销用发票.pdf")

        InvoiceParser(invoice_title_source="filename").parse(record, STANDARD_INVOICE_TEXT)

        self.assertEqual(record.invoice_title, "报销用发票")

    def test_missing_core_field_requires_review(self) -> None:
        record = self._record()
        text = """增值税电子普通发票
发票号码: 12345678901234567890
开票日期: 2026-05-01
购买方信息 名称: 北京示例科技有限公司
销售方信息 名称: 上海样例服务有限公司
"""

        InvoiceParser().parse(record, text)

        self.assertFalse(record.parse_success)
        self.assertIn("缺少金额", record.remarks)

    def test_no_valid_fields_gets_generic_remark_without_raw_text_preview(self) -> None:
        record = self._record()

        InvoiceParser().parse(record, "这是一段无法识别成发票字段的普通文本")

        self.assertFalse(record.parse_success)
        self.assertIn("未从文本中识别到有效发票字段", record.remarks)
        self.assertNotIn("原文预览", record.remarks)


if __name__ == "__main__":
    unittest.main()
