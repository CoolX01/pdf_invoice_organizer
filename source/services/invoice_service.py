from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from models.invoice_record import FileTask, InvoiceRecord
from parsers.invoice_parser import InvoiceParser
from parsers.pdf_text_extractor import PDFTextExtractor
from services.ocr_service import OCRService
from utils.file_utils import compute_file_hash
from utils.formatters import clean_text

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[int, int, str], None]]
LogCallback = Optional[Callable[[str], None]]
DUPLICATE_INVOICE_REMARK_PREFIX = "疑似重复发票（发票号码重复："


class InvoiceBatchProcessor:
    def __init__(
        self,
        enable_ocr: bool = True,
        ocr_confidence_threshold: float = 0.75,
        max_preview_text_chars: int = 1200,
        invoice_title_source: str = "filename",
    ) -> None:
        self.ocr_confidence_threshold = ocr_confidence_threshold
        self.max_preview_text_chars = max_preview_text_chars
        self.ocr_service = OCRService()
        self.extractor = PDFTextExtractor(
            ocr_service=self.ocr_service,
            enable_ocr=enable_ocr,
        )
        self.parser = InvoiceParser(invoice_title_source=invoice_title_source)

    def process_files(
        self,
        file_paths: list[Path],
        progress_callback: ProgressCallback = None,
        log_callback: LogCallback = None,
    ) -> list[InvoiceRecord]:
        file_hash_map: dict[str, Path] = {}
        tasks = self._build_tasks(file_paths, file_hash_map)
        records: list[InvoiceRecord] = []
        duplicate_file_count = sum(1 for task in tasks if task.duplicate_of is not None)

        total = len(tasks)
        for index, task in enumerate(tasks, start=1):
            if progress_callback:
                progress_callback(index - 1, total, f"正在处理：{task.path.name}")

            record = self._process_single(task, index)
            records.append(record)

            if log_callback:
                status = "成功" if record.parse_success else "失败"
                log_callback(f"{status}：{record.file_name} | 备注：{record.remarks or '无'}")

        self.refresh_duplicate_annotations(records)

        if progress_callback:
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
            except Exception as exc:
                logger.exception("Failed to hash file %s", path)
                file_hash = ""
                duplicate_of = None
            tasks.append(FileTask(path=path, duplicate_of=duplicate_of, file_hash=file_hash))
        return tasks

    def _process_single(self, task: FileTask, index: int) -> InvoiceRecord:
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

            if not record.parse_success:
                record.append_remark("关键信息识别不完整")
        except Exception as exc:
            logger.exception("Failed to process %s", task.path)
            record.mark_error(f"识别失败：{exc}")

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
            record.remove_remark_prefix(DUPLICATE_INVOICE_REMARK_PREFIX)

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
            normalized_invoice_number = clean_text(record.invoice_number).replace(" ", "")
            if normalized_invoice_number:
                grouped_records.setdefault(normalized_invoice_number, []).append(record)

        for duplicate_records in grouped_records.values():
            if len(duplicate_records) <= 1:
                continue

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
                record.append_remark(
                    f"{DUPLICATE_INVOICE_REMARK_PREFIX}与{duplicate_text}重复）"
                )
