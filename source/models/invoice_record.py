from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class InvoiceRecord:
    file_path: Path
    file_name: str
    index: int
    file_hash: str = ""
    invoice_number: str = ""
    total_amount: Optional[float] = None
    invoice_date: str = ""
    seller_name: str = ""
    buyer_name: str = ""
    item_name: str = ""
    invoice_title: str = ""
    invoice_type: str = ""
    remarks: str = ""
    raw_text_preview: str = ""
    parse_success: bool = False
    ocr_used: bool = False
    ocr_confidence: Optional[float] = None
    duplicate_file: bool = False
    duplicate_invoice: bool = False
    duplicate_invoice_conflict: bool = False
    errors: list[str] = field(default_factory=list)

    def append_remark(self, message: str) -> None:
        message = message.strip()
        if not message:
            return
        existing = {part.strip() for part in self.remarks.split("；") if part.strip()}
        if message not in existing:
            existing_list = [part.strip() for part in self.remarks.split("；") if part.strip()]
            existing_list.append(message)
            self.remarks = "；".join(existing_list)

    def remove_remark_prefix(self, prefix: str) -> None:
        items = [
            part.strip()
            for part in self.remarks.split("；")
            if part.strip() and not part.strip().startswith(prefix)
        ]
        self.remarks = "；".join(items)

    def mark_error(self, message: str) -> None:
        self.errors.append(message)
        self.append_remark(message)


@dataclass
class FileTask:
    path: Path
    duplicate_of: Optional[Path] = None
    file_hash: str = ""
