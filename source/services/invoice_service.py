from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import logging
from pathlib import Path
import re
from typing import Callable, Optional

from models.invoice_record import FileTask, InvoiceRecord
from parsers.invoice_parser import InvoiceParser
from parsers.pdf_text_extractor import PDFTextExtractor
from services.ocr_service import OCRService
from utils.file_utils import compute_file_hash
from utils.formatters import clean_text
from utils.logging_utils import safe_log_path

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[int, int, str], None]]
LogCallback = Optional[Callable[[str], None]]
CancelCallback = Optional[Callable[[], bool]]
DUPLICATE_INVOICE_REMARK_PREFIX = "疑似重复发票（发票号码重复："
DUPLICATE_INVOICE_CONFLICT_REMARK_PREFIX = "高风险重复发票（发票号码相同但金额/日期/销售方不一致："
FUTURE_DATE_TOLERANCE_DAYS = 7
CORE_FIELD_CONFLICT_PREFIX = "高风险：PDF文本/OCR"


class InvoiceBatchProcessor:
    def __init__(
        self,
        enable_ocr: bool = True,
        ocr_confidence_threshold: float = 0.75,
        max_preview_text_chars: int = 1200,
        invoice_title_source: str = "filename",
        max_ocr_pages: int = 10,
        ocr_render_scale: float = 2.0,
        ocr_try_variants: bool = True,
    ) -> None:
        self.ocr_confidence_threshold = ocr_confidence_threshold
        self.max_preview_text_chars = max_preview_text_chars
        self.ocr_service = OCRService()
        self.extractor = PDFTextExtractor(
            ocr_service=self.ocr_service,
            enable_ocr=enable_ocr,
            max_ocr_pages=max_ocr_pages,
            ocr_render_scale=ocr_render_scale,
            ocr_try_variants=ocr_try_variants,
        )
        self.parser = InvoiceParser(invoice_title_source=invoice_title_source)

    def process_files(
        self,
        file_paths: list[Path],
        progress_callback: ProgressCallback = None,
        log_callback: LogCallback = None,
        should_cancel: CancelCallback = None,
    ) -> list[InvoiceRecord]:
        file_hash_map: dict[str, Path] = {}
        tasks = self._build_tasks(file_paths, file_hash_map)
        records: list[InvoiceRecord] = []
        parsed_by_hash: dict[str, InvoiceRecord] = {}
        duplicate_file_count = sum(1 for task in tasks if task.duplicate_of is not None)

        total = len(tasks)
        for index, task in enumerate(tasks, start=1):
            if should_cancel and should_cancel():
                if log_callback:
                    log_callback(f"分析已取消：已处理 {len(records)} 个，未处理 {total - len(records)} 个。")
                break

            if progress_callback:
                progress_callback(index - 1, total, f"正在识别 {index}/{total}：{task.path.name}")

            record = self._process_single(task, index, parsed_by_hash)
            records.append(record)
            if record.file_hash and record.file_hash not in parsed_by_hash:
                parsed_by_hash[record.file_hash] = record

            if log_callback:
                status = "成功" if record.parse_success else "失败"
                log_callback(f"{status}：{record.file_name} | 备注：{record.remarks or '无'}")

        self.refresh_duplicate_annotations(records)

        if progress_callback and not (should_cancel and should_cancel()):
            progress_callback(total, total, "分析完成")

        success_count = sum(1 for item in records if item.parse_success)
        if log_callback:
            if duplicate_file_count:
                log_callback(f"发现相同PDF内容 {duplicate_file_count} 个，已保留处理，但不计入发票重复判断。")
            log_callback(f"共处理 {len(records)} 个文件，成功 {success_count} 个，失败 {len(records) - success_count} 个。")

        return records

    def _build_tasks(self, file_paths: list[Path], file_hash_map: dict[str, Path]) -> list[FileTask]:
        tasks: list[FileTask] = []
        for path in file_paths:
            duplicate_of = None
            file_hash = ""
            try:
                file_hash = compute_file_hash(path)
                duplicate_of = file_hash_map.get(file_hash)
                file_hash_map.setdefault(file_hash, path)
            except Exception:
                logger.warning("Failed to hash file %s", safe_log_path(path))
                file_hash = ""
                duplicate_of = None
            tasks.append(FileTask(path=path, duplicate_of=duplicate_of, file_hash=file_hash))
        return tasks

    def _process_single(
        self,
        task: FileTask,
        index: int,
        parsed_by_hash: Optional[dict[str, InvoiceRecord]] = None,
    ) -> InvoiceRecord:
        if task.duplicate_of is not None and task.file_hash and parsed_by_hash:
            cached_record = parsed_by_hash.get(task.file_hash)
            if cached_record is not None:
                record = replace(
                    cached_record,
                    file_path=task.path,
                    file_name=task.path.name,
                    index=index,
                    duplicate_file=True,
                    errors=list(cached_record.errors),
                )
                record.append_remark("相同 PDF 内容，已复用首次识别结果")
                return record

        record = InvoiceRecord(
            file_path=task.path,
            file_name=task.path.name,
            index=index,
            file_hash=task.file_hash,
        )

        if task.duplicate_of is not None:
            record.duplicate_file = True

        try:
            extraction = self.extractor.extract(task.path)
            text = extraction.text
            record.ocr_used = extraction.ocr_used
            record.ocr_confidence = extraction.ocr_confidence
            record.raw_text_preview = clean_text(text)[: self.max_preview_text_chars]

            for error in extraction.errors:
                record.append_remark(error)

            if extraction.ocr_used:
                record.append_remark(f"已使用 OCR（{extraction.ocr_engine}）")
                if (
                    extraction.ocr_confidence is not None
                    and extraction.ocr_confidence < self.ocr_confidence_threshold
                ):
                    record.append_remark(
                        f"OCR 置信度偏低（{extraction.ocr_confidence:.2f}）"
                    )

            if not clean_text(text):
                record.mark_error("识别失败")
                return record

            self.parser.parse(record, text)
            self._validate_record_fields(record)
            self._audit_with_ocr_if_needed(record, text, extraction)

            if not record.parse_success:
                record.append_remark("关键信息识别不完整")
        except Exception:
            logger.warning("Failed to process %s", safe_log_path(task.path))
            record.mark_error("识别失败：PDF 解析或 OCR 处理异常")

        return record

    @staticmethod
    def refresh_duplicate_annotations(records: list[InvoiceRecord]) -> None:
        InvoiceBatchProcessor._clear_duplicate_annotations(records)
        InvoiceBatchProcessor._mark_duplicate_files(records)
        InvoiceBatchProcessor._mark_duplicate_invoices(records)

    @staticmethod
    def count_duplicate_file_groups(records: list[InvoiceRecord]) -> int:
        groups = InvoiceBatchProcessor._group_records_by_file_hash(records)
        return sum(1 for duplicate_records in groups.values() if len(duplicate_records) > 1)

    @staticmethod
    def split_duplicate_file_records(
        records: list[InvoiceRecord],
    ) -> tuple[list[InvoiceRecord], list[InvoiceRecord]]:
        kept_records: list[InvoiceRecord] = []
        duplicate_records: list[InvoiceRecord] = []
        seen_hashes: set[str] = set()

        for record in records:
            if record.file_hash and record.file_hash in seen_hashes:
                duplicate_records.append(record)
                continue

            kept_records.append(record)
            if record.file_hash:
                seen_hashes.add(record.file_hash)

        return kept_records, duplicate_records

    @staticmethod
    def count_duplicate_file_removals(records: list[InvoiceRecord]) -> int:
        _, duplicate_records = InvoiceBatchProcessor.split_duplicate_file_records(records)
        return len(duplicate_records)

    @staticmethod
    def _clear_duplicate_annotations(records: list[InvoiceRecord]) -> None:
        for record in records:
            record.duplicate_file = False
            record.duplicate_invoice = False
            record.duplicate_invoice_conflict = False
            record.remove_remark_prefix(DUPLICATE_INVOICE_REMARK_PREFIX)
            record.remove_remark_prefix(DUPLICATE_INVOICE_CONFLICT_REMARK_PREFIX)

    @staticmethod
    def _group_records_by_file_hash(records: list[InvoiceRecord]) -> dict[str, list[InvoiceRecord]]:
        grouped_records: dict[str, list[InvoiceRecord]] = {}
        for record in records:
            if not record.file_hash:
                continue
            grouped_records.setdefault(record.file_hash, []).append(record)
        return grouped_records

    @staticmethod
    def _mark_duplicate_files(records: list[InvoiceRecord]) -> None:
        grouped_records = InvoiceBatchProcessor._group_records_by_file_hash(records)
        for duplicate_records in grouped_records.values():
            if len(duplicate_records) <= 1:
                continue
            for record in duplicate_records[1:]:
                record.duplicate_file = True

    @staticmethod
    def _mark_duplicate_invoices(records: list[InvoiceRecord]) -> None:
        grouped_records: dict[str, list[InvoiceRecord]] = {}
        for record in records:
            if record.duplicate_file:
                continue
            normalized_invoice_number = clean_text(record.invoice_number).replace(" ", "")
            if normalized_invoice_number:
                grouped_records.setdefault(normalized_invoice_number, []).append(record)

        for duplicate_records in grouped_records.values():
            if len(duplicate_records) <= 1:
                continue

            signatures = {
                InvoiceBatchProcessor._invoice_duplicate_signature(record)
                for record in duplicate_records
            }
            has_conflict = len(signatures) > 1

            for record in duplicate_records:
                duplicate_targets = [
                    f"序号{other.index} 文件{other.file_name}"
                    for other in duplicate_records
                    if other is not record
                ]
                if not duplicate_targets:
                    continue

                record.duplicate_invoice = True
                duplicate_text = "、".join(duplicate_targets)
                if has_conflict:
                    record.duplicate_invoice_conflict = True
                    record.append_remark(
                        f"{DUPLICATE_INVOICE_CONFLICT_REMARK_PREFIX}请重点复核，涉及{duplicate_text}）"
                    )
                else:
                    record.append_remark(
                        f"{DUPLICATE_INVOICE_REMARK_PREFIX}与{duplicate_text}重复）"
                    )

    @staticmethod
    def _invoice_duplicate_signature(record: InvoiceRecord) -> tuple[object, ...]:
        amount = round(record.total_amount, 2) if record.total_amount is not None else None
        return (
            amount,
            clean_text(record.invoice_date),
            clean_text(record.seller_name),
        )

    @staticmethod
    def _validate_record_fields(record: InvoiceRecord) -> None:
        if record.total_amount is not None and record.total_amount <= 0:
            if record.total_amount == 0:
                record.parse_success = False
                record.append_remark("金额异常（应不为 0）")
            elif not InvoiceBatchProcessor._is_red_invoice_record(record):
                record.parse_success = False
                record.append_remark("金额异常（负数金额需为红字发票）")

        if record.invoice_number:
            normalized_invoice_number = clean_text(record.invoice_number).replace(" ", "")
            if not normalized_invoice_number.isdigit() or not (8 <= len(normalized_invoice_number) <= 20):
                record.parse_success = False
                record.append_remark("发票号码格式异常")

        if record.invoice_date:
            try:
                invoice_date = datetime.strptime(record.invoice_date, "%Y-%m-%d").date()
            except ValueError:
                record.parse_success = False
                record.append_remark("开票日期格式异常")
            else:
                max_allowed_date = date.today() + timedelta(days=FUTURE_DATE_TOLERANCE_DAYS)
                if invoice_date > max_allowed_date:
                    record.parse_success = False
                    record.append_remark("开票日期异常（晚于当前日期超过 7 天）")

    @staticmethod
    def _is_red_invoice_record(record: InvoiceRecord) -> bool:
        text = clean_text(" ".join([record.raw_text_preview, record.invoice_type, record.remarks]))
        return "红字发票" in text or "负数" in text or "被红冲" in text

    def _audit_with_ocr_if_needed(
        self,
        record: InvoiceRecord,
        source_text: str,
        extraction,
    ) -> None:
        if extraction.ocr_used or not self.extractor.enable_ocr:
            return

        trigger_reasons = self._ocr_audit_trigger_reasons(record, source_text)
        if not trigger_reasons:
            return

        ocr_extraction = self.extractor.extract_ocr(record.file_path)
        record.ocr_used = True
        record.ocr_confidence = ocr_extraction.ocr_confidence

        if ocr_extraction.errors:
            for reason in trigger_reasons:
                record.append_remark(reason)
            for error in ocr_extraction.errors:
                record.append_remark(error)
            return

        if (
            ocr_extraction.ocr_confidence is not None
            and ocr_extraction.ocr_confidence < self.ocr_confidence_threshold
        ):
            record.append_remark(f"OCR 置信度偏低（{ocr_extraction.ocr_confidence:.2f}）")

        ocr_record = InvoiceRecord(
            file_path=record.file_path,
            file_name=record.file_name,
            index=record.index,
            file_hash=record.file_hash,
        )
        ocr_record.ocr_used = True
        ocr_record.ocr_confidence = ocr_extraction.ocr_confidence
        ocr_record.raw_text_preview = clean_text(ocr_extraction.text)[: self.max_preview_text_chars]
        self.parser.parse(ocr_record, ocr_extraction.text)
        self._validate_record_fields(ocr_record)

        changed = self._merge_ocr_candidate(record, ocr_record, trigger_reasons)
        self._validate_record_fields(record)
        self._refresh_parse_success(record)
        if changed:
            record.append_remark("OCR自动复核并补全字段")
        elif not self._has_core_field_conflict(record) and "已自动触发 OCR 复核" not in record.remarks:
            record.append_remark("OCR自动复核通过")

    def _ocr_audit_trigger_reasons(self, record: InvoiceRecord, source_text: str) -> list[str]:
        reasons: list[str] = []
        if not record.parse_success:
            reasons.append("关键字段不完整，已自动触发 OCR 复核")

        for field_name, value in (
            ("购买方名称", record.buyer_name),
            ("销售方名称", record.seller_name),
        ):
            issue = self._party_name_issue(field_name, value)
            if issue:
                reasons.append(issue)

        normalized = clean_text(source_text)
        layout_risk_tokens = (
            "购 销 买 名称",
            "方 方 信",
            "买方信息 名称",
            "销售方信息 下载次数",
        )
        if any(token in normalized for token in layout_risk_tokens):
            reasons.append("PDF文本层疑似版式错序，已自动触发 OCR 复核")

        return self._deduplicate_messages(reasons)

    @staticmethod
    def _party_name_issue(field_name: str, value: str) -> str:
        normalized = clean_text(value)
        if not normalized:
            return f"{field_name}缺失，已自动触发 OCR 复核"

        compact = normalized.replace(" ", "")
        risky_tokens = (
            "统一社会信用代码",
            "纳税人识别号",
            "购买方信息",
            "销售方信息",
            "项目名称",
            "规格型号",
            "下载次数",
            "开票人",
            "方方信",
            "信息统一",
        )
        if any(token in compact for token in risky_tokens):
            return f"{field_name}异常（疑似串入其他字段），已自动触发 OCR 复核"

        if InvoiceBatchProcessor._looks_like_tax_identifier(compact):
            return f"{field_name}异常（疑似税号），已自动触发 OCR 复核"

        return ""

    @staticmethod
    def _looks_like_tax_identifier(value: str) -> bool:
        return bool(value and re.fullmatch(r"[0-9A-Z]{15,20}", value))

    def _merge_ocr_candidate(
        self,
        record: InvoiceRecord,
        ocr_record: InvoiceRecord,
        trigger_reasons: list[str],
    ) -> bool:
        changed = False
        core_specs = [
            ("invoice_number", "发票号码", self._same_invoice_number),
            ("total_amount", "金额", self._same_amount),
            ("invoice_date", "开票日期", self._same_text),
        ]

        for attr, label, same_func in core_specs:
            current_value = getattr(record, attr)
            ocr_value = getattr(ocr_record, attr)
            if not current_value and ocr_value:
                setattr(record, attr, ocr_value)
                self._remove_resolved_missing_remark(record, label)
                record.append_remark(f"OCR自动补全{label}")
                changed = True
                continue
            if current_value and ocr_value and not same_func(current_value, ocr_value):
                record.append_remark(
                    f"{CORE_FIELD_CONFLICT_PREFIX}{label}不一致（PDF：{current_value}，OCR：{ocr_value}）"
                )

        for attr, label in (
            ("buyer_name", "购买方名称"),
            ("seller_name", "销售方名称"),
        ):
            current_value = getattr(record, attr)
            ocr_value = getattr(ocr_record, attr)
            current_score = self._party_name_quality_score(current_value)
            ocr_score = self._party_name_quality_score(ocr_value)
            if ocr_value and (
                (not current_value and ocr_score > 0)
                or (current_value and ocr_score >= 2 and ocr_score > current_score)
            ):
                setattr(record, attr, ocr_value)
                self._remove_resolved_missing_remark(record, label)
                record.append_remark(f"OCR自动修正{label}")
                changed = True
                continue
            if (
                current_value
                and ocr_value
                and current_score >= 2
                and ocr_score >= 2
                and self._text_similarity(current_value, ocr_value) < 0.65
            ):
                record.append_remark(f"{label}异常（PDF文本/OCR差异较大）")

        unresolved_reasons = [
            reason
            for reason in trigger_reasons
            if self._trigger_reason_still_unresolved(record, reason)
        ]
        for reason in unresolved_reasons:
            record.append_remark(reason)

        return changed

    @staticmethod
    def _same_invoice_number(left, right) -> bool:
        return clean_text(str(left)).replace(" ", "") == clean_text(str(right)).replace(" ", "")

    @staticmethod
    def _same_amount(left, right) -> bool:
        try:
            return abs(float(left) - float(right)) <= 0.01
        except (TypeError, ValueError):
            return left == right

    @staticmethod
    def _same_text(left, right) -> bool:
        return clean_text(str(left)) == clean_text(str(right))

    @staticmethod
    def _party_name_quality_score(value: str) -> int:
        normalized = clean_text(value)
        if not normalized:
            return 0

        compact = normalized.replace(" ", "")
        score = 1
        if any(suffix in normalized for suffix in ("公司", "企业", "店", "中心", "出版社")):
            score += 3
        if any("\u4e00" <= char <= "\u9fff" for char in normalized):
            score += 1
        if InvoiceBatchProcessor._party_name_issue("字段", normalized):
            score -= 4
        if len(compact) > 45:
            score -= 2
        return score

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        return SequenceMatcher(
            None,
            clean_text(left).replace(" ", ""),
            clean_text(right).replace(" ", ""),
        ).ratio()

    @staticmethod
    def _remove_resolved_missing_remark(record: InvoiceRecord, label: str) -> None:
        missing_map = {
            "发票号码": "缺少发票号码",
            "金额": "缺少金额",
            "开票日期": "缺少日期",
            "购买方名称": "缺少购买方名称",
            "销售方名称": "缺少销售方名称",
        }
        prefix = missing_map.get(label)
        if prefix:
            record.remove_remark_prefix(prefix)
        if label == "金额":
            record.remove_remark_prefix("金额异常")
        record.remove_remark_prefix("关键信息识别不完整")

    @staticmethod
    def _refresh_parse_success(record: InvoiceRecord) -> None:
        if not (record.invoice_number and record.total_amount is not None and record.invoice_date):
            record.parse_success = False
            return
        if any(
            token in record.remarks
            for token in (
                "金额异常",
                "发票号码格式异常",
                "开票日期格式异常",
                "开票日期异常",
            )
        ):
            record.parse_success = False
            return
        record.parse_success = True

    @staticmethod
    def _trigger_reason_still_unresolved(record: InvoiceRecord, reason: str) -> bool:
        if "关键字段不完整" in reason:
            return not record.parse_success
        if "购买方名称" in reason:
            return bool(InvoiceBatchProcessor._party_name_issue("购买方名称", record.buyer_name))
        if "销售方名称" in reason:
            return bool(InvoiceBatchProcessor._party_name_issue("销售方名称", record.seller_name))
        return False

    @staticmethod
    def _has_core_field_conflict(record: InvoiceRecord) -> bool:
        return CORE_FIELD_CONFLICT_PREFIX in record.remarks

    @staticmethod
    def _deduplicate_messages(messages: list[str]) -> list[str]:
        deduplicated: list[str] = []
        for message in messages:
            if message and message not in deduplicated:
                deduplicated.append(message)
        return deduplicated
