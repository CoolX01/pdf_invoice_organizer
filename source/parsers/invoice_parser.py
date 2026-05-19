from __future__ import annotations

import re

from models.invoice_record import InvoiceRecord
from utils.formatters import clean_text, normalize_amount, normalize_date


class InvoiceParser:
    def __init__(self, invoice_title_source: str = "filename") -> None:
        self.invoice_title_source = invoice_title_source

    def parse(self, record: InvoiceRecord, raw_text: str) -> InvoiceRecord:
        text = raw_text or ""
        compact = clean_text(text)

        record.invoice_number = self._extract_invoice_number(text)
        record.total_amount = self._extract_total_amount(text)
        record.invoice_date = normalize_date(self._extract_invoice_date(text))
        record.buyer_name = self._extract_party_name(text, party="buyer")
        record.seller_name = self._extract_party_name(text, party="seller")
        record.item_name = self._extract_item_name(text)
        record.invoice_type = self._extract_invoice_title(text)
        record.invoice_title = self._resolve_invoice_title(record)

        if not record.invoice_number:
            record.append_remark("缺少发票号码")
        if record.total_amount is None:
            record.append_remark("缺少金额")
        if not record.invoice_date:
            record.append_remark("缺少日期")
        if not record.buyer_name:
            record.append_remark("缺少购买方名称")
        if not record.seller_name:
            record.append_remark("缺少销售方名称")

        recognized_fields = [
            record.invoice_number,
            record.total_amount,
            record.invoice_date,
            record.seller_name,
            record.buyer_name,
            record.item_name,
        ]

        # 发票号、金额和日期是后续去重、汇总、导出的核心字段。
        # 不能只因为 OCR 识别到任意一个字段就把发票计为“成功”，否则
        # 只有日期/项目名的严重缺失记录也会被用户误认为已完整识别。
        record.parse_success = bool(
            record.invoice_number
            and record.total_amount is not None
            and record.invoice_date
        )

        if compact and not any(bool(value) for value in recognized_fields):
            record.append_remark("未从文本中识别到有效发票字段")

        return record

    def _resolve_invoice_title(self, record: InvoiceRecord) -> str:
        if self.invoice_title_source == "invoice_type":
            return record.invoice_type or record.file_path.stem
        return record.file_path.stem or record.invoice_type

    def _extract_invoice_number(self, text: str) -> str:
        normalized = clean_text(text)
        patterns = [
            r"发票号码[:：]?\s*([0-9]{8,20})",
            r"票据号码[:：]?\s*([0-9]{8,20})",
            r"号码[:：]?\s*([0-9]{8,20})",
            r"发票号[:：]?\s*([0-9]{8,20})",
        ]
        return self._first_match(text, patterns) or self._first_match(normalized, patterns)

    def _extract_total_amount(self, text: str):
        normalized = clean_text(text)
        amount_pattern = r"([-+]?[0-9][0-9.,]*)"
        patterns = [
            rf"价税合计[（(]小写[)）][:：]?\s*[¥￥]?\s*{amount_pattern}",
            rf"价税合计[^¥￥0-9-]{{0,12}}[¥￥]\s*{amount_pattern}",
            rf"价税合计[^\n]{{0,20}}[（(]小写[)）][^0-9¥￥-]*{amount_pattern}",
            rf"[（(]小写[)）]\s*[¥￥]?\s*{amount_pattern}",
            rf"小写[^0-9¥￥-]{{0,6}}[¥￥]?\s*{amount_pattern}",
            rf"小写[:：]?\s*[¥￥]?\s*{amount_pattern}",
            rf"合计[:：]?\s*[¥￥]?\s*{amount_pattern}",
        ]
        for source in (text, normalized):
            for pattern in patterns:
                match = re.search(pattern, source, re.IGNORECASE)
                if match:
                    amount = normalize_amount(match.group(1))
                    if amount is not None:
                        return amount
        return None

    def _extract_invoice_date(self, text: str) -> str:
        normalized = clean_text(text)
        patterns = [
            r"开票日期[:：]?\s*(20\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?)",
            r"日期[:：]?\s*(20\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?)",
            r"出票日期[:：]?\s*(20\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?)",
        ]
        matched = self._first_match(text, patterns) or self._first_match(normalized, patterns)
        if matched:
            return matched

        general_date_pattern = r"(20\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?)"
        for raw_line in text.splitlines()[:15]:
            line = clean_text(raw_line)
            if not line:
                continue
            if "日期" in line or "发票" in line or "票号" in line:
                match = re.search(general_date_pattern, line)
                if match:
                    return clean_text(match.group(1))

        header_text = "\n".join(text.splitlines()[:15])
        match = re.search(general_date_pattern, header_text)
        if match:
            return clean_text(match.group(1))
        return ""

    def _extract_party_name(self, text: str, party: str) -> str:
        normalized = clean_text(text)
        paired_names = self._extract_party_names_from_same_line(text)
        if paired_names:
            buyer_name, seller_name = paired_names
            return buyer_name if party == "buyer" else seller_name

        if party == "buyer":
            anchors = ["购买方信息", "购买方", "购 方 信 息"]
            compact_patterns = [
                r"(?:购买方信息|购买方|购方)[^。]{0,20}?名称[:：]?\s*(.+?)(?=\s+(?:销|售|销售方)\s*名称[:：]|\s+(?:统一社会信用代码|纳税人识别号|项目名称|备注|开票人|下载次数|$))",
                r"(?:购|买)\s*名称[:：]?\s*(.+?)(?=\s+(?:销|售)\s*名称[:：]|\s+(?:统一社会信用代码|纳税人识别号|项目名称|备注|开票人|下载次数|$))",
            ]
        else:
            anchors = ["销售方信息", "销售方", "销 方 信 息"]
            compact_patterns = [
                r"(?:销售方信息|销售方|销方)[^。]{0,20}?名称[:：]?\s*(.+?)(?=\s+(?:统一社会信用代码|纳税人识别号|项目名称|备注|开票人|下载次数|$))",
                r"(?:销|售)\s*名称[:：]?\s*(.+?)(?=\s+(?:统一社会信用代码|纳税人识别号|项目名称|备注|开票人|下载次数|$))",
            ]

        compact_match = self._first_match(normalized, compact_patterns)
        if compact_match:
            return self._sanitize_party_name(compact_match)

        for anchor in anchors:
            block = self._extract_block_after_anchor(text, anchor)
            if not block:
                continue
            match = re.search(r"名称[:：]?\s*([^\n]+)", block)
            if match:
                return self._sanitize_party_name(match.group(1))
            lines = [clean_text(line) for line in block.splitlines() if clean_text(line)]
            for line in lines:
                if len(line) >= 4 and "税号" not in line and "识别号" not in line:
                    return self._sanitize_party_name(line)

        fallback_patterns = [
            rf"{'购买方' if party == 'buyer' else '销售方'}名称[:：]?\s*([^\n]+)",
            rf"{'购方' if party == 'buyer' else '销方'}名称[:：]?\s*([^\n]+)",
            rf"{'购买方' if party == 'buyer' else '销售方'}[^\n]{{0,12}}名称[:：]?\s*([^\n]+)",
        ]
        matched = self._first_match(text, fallback_patterns) or self._first_match(normalized, fallback_patterns)
        if matched:
            return self._sanitize_party_name(matched)

        block_patterns = [
            rf"{'购买方' if party == 'buyer' else '销售方'}[\s\S]{{0,80}}?名称[:：]?\s*([^\n]+)",
            rf"{'购买方' if party == 'buyer' else '销售方'}[\s\S]{{0,120}}?([^\n]+公司)",
        ]
        block_matched = self._first_match(text, block_patterns) or self._first_match(normalized, block_patterns)
        return self._sanitize_party_name(block_matched)

    def _extract_party_names_from_same_line(self, text: str) -> tuple[str, str] | None:
        normalized = clean_text(text)
        pair_patterns = [
            r"(?:购买方信息|买方信息|购买方|购方)[^\n。]{0,50}?名称[:：]?\s*(.+?)\s+名称[:：]?\s*(.+?)(?=\s+(?:统一社会信用代码|纳税人识别号|项目名称|规格型号|下载次数|备注|$))",
            r"(?:购买方信息|买方信息|购买方|购方)[\s\S]{0,120}?名称[:：]?\s*(.+?)(?=\s+(?:销售方信息|销售方|销方)[\s\S]{0,40}?名称[:：])[\s\S]{0,120}?(?:销售方信息|销售方|销方)[\s\S]{0,40}?名称[:：]?\s*(.+?)(?=\s+(?:统一社会信用代码|纳税人识别号|项目名称|规格型号|下载次数|备注|$))",
            r"购\s+销\s+买\s+名称[:：]?\s*(.+?)\s+售\s+名称[:：]?\s*(.+?)(?=\s+方|\s+统一社会信用代码|\s+纳税人识别号|\s+项目名称|$)",
        ]
        for source in (normalized, text):
            for pattern in pair_patterns:
                match = re.search(pattern, source, re.IGNORECASE)
                if not match:
                    continue
                buyer_name = self._sanitize_party_name(match.group(1))
                seller_name = self._sanitize_party_name(match.group(2))
                if buyer_name or seller_name:
                    return buyer_name, seller_name

        for raw_line in text.splitlines():
            if raw_line.count("名称") < 2:
                continue
            match = re.search(
                r"名称[:：]\s*(.+?)\s{2,}名称[:：]\s*(.+)$",
                raw_line.strip(),
            )
            if not match:
                continue
            buyer_name = self._sanitize_party_name(match.group(1))
            seller_name = self._sanitize_party_name(match.group(2))
            if buyer_name or seller_name:
                return buyer_name, seller_name
        return None

    def _extract_item_name(self, text: str) -> str:
        item_lines: list[str] = []
        for raw_line in text.splitlines():
            line = clean_text(raw_line)
            if not line or not line.startswith("*"):
                continue
            if "项目名称" in line or "税率" in line:
                continue
            compact_match = re.match(r"(\*[^\d\n]+?)(?=\s{2,}|$)", raw_line.strip())
            item_lines.append(clean_text(compact_match.group(1) if compact_match else line))

        if item_lines:
            deduplicated: list[str] = []
            for line in item_lines:
                if line not in deduplicated:
                    deduplicated.append(line)
            if len(deduplicated) <= 3:
                return "；".join(deduplicated)
            return "；".join(deduplicated[:3]) + f" 等{len(deduplicated)}项"

        patterns = [
            r"项目名称[:：]?\s*([^\n]+)",
            r"货物或应税劳务、服务名称[:：]?\s*([^\n]+)",
        ]
        matched = self._first_match(text, patterns)
        if matched and not self._looks_like_header(matched):
            return matched

        line_match = re.search(r"(\*[^\n]{2,80})", text)
        if line_match:
            return clean_text(line_match.group(1))
        return ""

    def _extract_invoice_title(self, text: str) -> str:
        patterns = [
            r"(增值税电子普通发票)",
            r"(增值税普通发票)",
            r"(增值税专用发票)",
            r"(电子发票[（(]普通发票[)）])",
            r"(电子发票[（(]增值税普通发票[)）])",
            r"(电子发票[（(]增值税专用发票[)）])",
            r"(电子发票[（(]专用发票[)）])",
            r"(全电发票)",
            r"(电子发票)",
        ]
        return self._first_match(text, patterns)

    def _extract_block_after_anchor(self, text: str, anchor: str) -> str:
        match = re.search(
            rf"{re.escape(anchor)}[\s\S]{{0,180}}?(?=(购买方信息|销售方信息|备注|密码区|项目名称|$))",
            text,
        )
        return match.group(0) if match else ""

    def _first_match(self, text: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return clean_text(match.group(1))
        return ""

    def _sanitize_party_name(self, value: str) -> str:
        value = clean_text(value)
        if not value:
            return ""
        value = re.split(
            r"\s+(?=(?:销|售|销售方)\s*名称[:：]|(?:统一社会信用代码|纳税人识别号|项目名称|备注|开票人|下载次数|$))",
            value,
            maxsplit=1,
        )[0]
        value = re.sub(r"\s+(?:买|卖|销|售|方|信|息)(?:\s+(?:买|卖|销|售|方|信|息))*$", "", value)
        return value.strip("：: ")

    def _looks_like_header(self, value: str) -> bool:
        header_tokens = ["规格型号", "单 位", "数量", "单价", "金额", "税率", "税额"]
        return any(token in value for token in header_tokens)
