from __future__ import annotations

from pathlib import Path

from qt_compat import QThread, Signal

from services.invoice_service import InvoiceBatchProcessor


class AnalysisWorker(QThread):
    progress_changed = Signal(int, int, str)
    log_emitted = Signal(str)
    finished_with_results = Signal(object)
    failed = Signal(str)

    def __init__(self, file_paths: list[Path], options: dict) -> None:
        super().__init__()
        self.file_paths = file_paths
        self.options = options

    def run(self) -> None:
        try:
            processor = InvoiceBatchProcessor(
                enable_ocr=self.options.get("ocr_enabled", True),
                ocr_confidence_threshold=self.options.get("ocr_confidence_threshold", 0.75),
                max_preview_text_chars=self.options.get("max_preview_text_chars", 1200),
                invoice_title_source=self.options.get("invoice_title_source", "filename"),
            )
            records = processor.process_files(
                self.file_paths,
                progress_callback=self._on_progress,
                log_callback=self.log_emitted.emit,
            )
            self.finished_with_results.emit(records)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress_changed.emit(current, total, message)
