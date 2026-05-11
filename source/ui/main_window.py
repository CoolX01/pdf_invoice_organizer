from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from qt_compat import (
    QAbstractItemView,
    QFileDialog,
    QFile,
    QDragEnterEvent,
    QDropEvent,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    Qt,
    QVBoxLayout,
    QWidget,
)

from exporters.excel_exporter import ExcelExporter
from models.invoice_record import InvoiceRecord
from services.invoice_service import InvoiceBatchProcessor
from ui.workers import AnalysisWorker
from utils.config import AppConfig
from utils.constants import PREVIEW_HEADERS
from utils.file_utils import desktop_dir, is_pdf_file

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.config = AppConfig(base_dir)
        self.exporter = ExcelExporter()
        self.selected_files: list[Path] = []
        self.target_folder: Path | None = None
        self.target_folder_files: list[Path] = []
        self.file_statuses: dict[str, str] = {}
        self.records: list[InvoiceRecord] = []
        self.analysis_completed = False
        self.worker: AnalysisWorker | None = None
        self.last_exported_path: Path | None = None
        self.last_export_signature: tuple | None = None

        self.setWindowTitle("PDF发票自动整理归纳工具")
        self.setMinimumSize(1280, 820)
        self.setAcceptDrops(True)

        self.output_path = self._initial_output_path()
        self.template_path = None

        self._build_ui()
        self._refresh_button_states()
        self._append_log("软件已启动，可添加 PDF 文件开始使用。")

    def _build_ui(self) -> None:
        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        top_panel = self._build_top_panel()
        queue_panel = self._build_queue_panel()
        results_panel = self._build_results_panel()
        bottom_panel = self._build_bottom_panel()

        queue_panel.setFixedHeight(122)
        bottom_panel.setFixedHeight(170)
        results_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        root_layout.addWidget(top_panel)
        root_layout.addWidget(queue_panel)
        root_layout.addWidget(results_panel, 1)
        root_layout.addWidget(bottom_panel)

        self.setCentralWidget(central_widget)
        self._apply_styles()

    def _build_top_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("TopPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.folder_button = QPushButton("选择文件夹")
        self.folder_button.clicked.connect(self.choose_folder)
        button_row.addWidget(self.folder_button)

        self.output_button = QPushButton("输出路径选择")
        self.output_button.clicked.connect(self.choose_output_path)
        button_row.addWidget(self.output_button)

        self.file_count_label = QLabel("当前文件：0")
        button_row.addWidget(self.file_count_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(180)
        button_row.addWidget(self.progress_bar)

        self.status_label = QLabel("状态：待命")
        self.status_label.setMinimumWidth(170)
        button_row.addWidget(self.status_label)

        layout.addLayout(button_row)

        self.output_path_label = QLabel(f"输出路径：{self.output_path}")
        self.output_path_label.setWordWrap(True)
        layout.addWidget(self.output_path_label)

        hint = QLabel("支持选择文件夹导入，也支持直接把 PDF 文件拖拽到窗口中。")
        hint.setObjectName("HintLabel")
        layout.addWidget(hint)
        return panel

    def _build_results_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("ResultsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self.start_button = QPushButton("开始分析")
        self.start_button.setObjectName("PrimaryActionButton")
        self.start_button.clicked.connect(self.start_analysis)
        title_row.addWidget(self.start_button)

        title = QLabel("解析结果预览")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)

        self.total_amount_label = QLabel("总金额：0.00 元")
        self.total_amount_label.setObjectName("AmountSummary")
        title_row.addWidget(self.total_amount_label)

        self.duplicate_count_label = QLabel("重复组数：0")
        self.duplicate_count_label.setObjectName("AmountSummary")
        title_row.addWidget(self.duplicate_count_label)

        self.remove_duplicates_button = QPushButton("删除重复文件")
        self.remove_duplicates_button.setObjectName("HeaderActionButton")
        self.remove_duplicates_button.clicked.connect(self.remove_duplicate_files)
        title_row.addWidget(self.remove_duplicates_button)

        self.delete_local_duplicates_button = QPushButton("删除本地重复文件")
        self.delete_local_duplicates_button.setObjectName("DangerActionButton")
        self.delete_local_duplicates_button.clicked.connect(self.delete_duplicate_local_files)
        title_row.addWidget(self.delete_local_duplicates_button)

        self.export_button = QPushButton("输出Excel")
        self.export_button.setObjectName("PrimaryActionButton")
        self.export_button.clicked.connect(self.export_excel)
        title_row.addWidget(self.export_button)

        self.clear_button = QPushButton("清空列表")
        self.clear_button.setObjectName("HeaderActionButton")
        self.clear_button.clicked.connect(self.clear_files)
        title_row.addWidget(self.clear_button)

        title_row.addStretch(1)

        layout.addLayout(title_row)

        self.table = QTableWidget(0, len(PREVIEW_HEADERS))
        self.table.setHorizontalHeaderLabels(PREVIEW_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        default_widths = [70, 220, 180, 120, 110, 220, 220, 260]
        for column, width in enumerate(default_widths):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        return panel

    def _build_queue_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("QueuePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = QLabel("待处理文件")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)

        self.queue_count_label = QLabel("数量：0")
        self.queue_count_label.setObjectName("AmountSummary")
        title_row.addWidget(self.queue_count_label)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setFixedHeight(72)
        self.file_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.file_list_widget)
        return panel

    def _build_bottom_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("BottomPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        log_title = QLabel("日志 / 状态")
        log_title.setObjectName("SectionTitle")
        layout.addWidget(log_title)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(112)
        layout.addWidget(self.log_box)
        return panel

    def choose_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择 PDF 文件",
            str(Path.home()),
            "PDF Files (*.pdf)",
        )
        if file_paths:
            self._add_files([Path(path) for path in file_paths])

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择包含 PDF 的文件夹",
            str(Path.home()),
        )
        if not folder:
            return

        folder_path = Path(folder)
        file_paths = sorted(
            [path for path in folder_path.rglob("*") if is_pdf_file(path)],
            key=lambda item: item.name.lower(),
        )
        if not file_paths:
            self._warn("提示", "所选文件夹中未找到 PDF 文件。")
            return

        self.target_folder = folder_path
        self._set_target_folder_files(file_paths)
        self.file_statuses.clear()
        self.analysis_completed = False
        self.records = []
        self.table.setRowCount(0)
        self._update_total_amount_label([])
        self._append_log(
            f"已选择目标文件夹：{folder_path}，当前待处理文件 {len(self.selected_files)} 个。"
        )
        self._refresh_file_queue()
        self._refresh_button_states()

    def choose_output_path(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择 Excel 输出路径",
            str(self.output_path),
            "Excel Files (*.xlsx)",
        )
        if file_path:
            self.output_path = Path(file_path)
            if self.output_path.suffix.lower() != ".xlsx":
                self.output_path = self.output_path.with_suffix(".xlsx")
            self.output_path_label.setText(f"输出路径：{self.output_path}")
            self.config.set("default_output_dir", str(self.output_path.parent))
            self.config.save()
            self._append_log(f"已设置输出路径：{self.output_path}")

    def clear_files(self) -> None:
        if self.worker and self.worker.isRunning():
            self._warn("提示", "分析进行中，暂不支持清空列表。")
            return

        self.selected_files.clear()
        self.target_folder = None
        self.target_folder_files.clear()
        self.file_statuses.clear()
        self.records.clear()
        self.analysis_completed = False
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：待命")
        self._update_total_amount_label([])
        self.file_count_label.setText("当前文件：0")
        self.queue_count_label.setText("数量：0")
        self._refresh_file_queue()
        self._refresh_button_states()
        self._append_log("已清空文件列表和分析结果。")

    def remove_duplicate_files(self) -> None:
        if not self.analysis_completed or not self.records:
            self._warn("提示", "请先完成分析，再删除重复文件。")
            return

        duplicate_group_count = InvoiceBatchProcessor.count_duplicate_file_groups(self.records)
        kept_records, removed_records = InvoiceBatchProcessor.split_duplicate_file_records(self.records)
        duplicate_remove_count = len(removed_records)
        if duplicate_remove_count <= 0:
            self._warn("提示", "当前没有可删除的重复文件。")
            return

        reply = QMessageBox.question(
            self,
            "删除重复文件",
            (
                f"检测到 {duplicate_group_count} 组相同 PDF 内容，"
                f"将删除 {duplicate_remove_count} 个重复文件，"
                "每组仅保留第一份。\n\n是否继续？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._replace_records(kept_records)

        preview_names = "、".join(record.file_name for record in removed_records[:5])
        if len(removed_records) > 5:
            preview_names = f"{preview_names} 等 {len(removed_records)} 个文件"
        self._append_log(
            f"已删除 {duplicate_remove_count} 个重复文件，保留 {len(kept_records)} 个文件。"
        )
        if preview_names:
            self._append_log(f"已移除的文件：{preview_names}")

        QMessageBox.information(
            self,
            "删除完成",
            f"已删除 {duplicate_remove_count} 个重复文件，当前保留 {len(kept_records)} 个文件。",
        )

    def delete_duplicate_local_files(self) -> None:
        if not self.analysis_completed or not self.records:
            self._warn("提示", "请先完成分析，再删除本地重复文件。")
            return

        duplicate_group_count = InvoiceBatchProcessor.count_duplicate_file_groups(self.records)
        _, duplicate_records = InvoiceBatchProcessor.split_duplicate_file_records(self.records)
        duplicate_remove_count = len(duplicate_records)
        if duplicate_remove_count <= 0:
            self._warn("提示", "当前没有可删除的本地重复文件。")
            return

        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.setWindowTitle("删除本地重复文件")
        message_box.setText(
            (
                f"检测到 {duplicate_group_count} 组相同 PDF 内容，"
                f"将把 {duplicate_remove_count} 个本地重复文件移到系统回收站/废纸篓，"
                "每组仅保留第一份。"
            )
        )
        message_box.setInformativeText(
            "该操作会同时把这些文件从当前分析结果中移除。展开“显示详情”可查看完整删除清单。"
        )
        message_box.setDetailedText(self._build_local_delete_detail_text(duplicate_records))
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        if message_box.exec() != QMessageBox.StandardButton.Yes:
            return

        removed_ids: set[int] = set()
        removed_names: list[str] = []
        failed_messages: list[str] = []

        for record in duplicate_records:
            success, detail = self._move_file_to_trash(record.file_path)
            if success:
                removed_ids.add(id(record))
                removed_names.append(record.file_name)
                continue

            error_text = detail or "无法移到系统回收站/废纸篓"
            failed_messages.append(f"{record.file_name}：{error_text}")

        if not removed_ids:
            error_preview = "；".join(failed_messages[:3]) if failed_messages else "没有文件被删除。"
            self._warn("删除失败", error_preview)
            self._append_log(f"删除本地重复文件失败：{error_preview}")
            return

        remaining_records = [record for record in self.records if id(record) not in removed_ids]
        self._replace_records(remaining_records)

        self._append_log(
            f"已将 {len(removed_names)} 个本地重复文件移到系统回收站/废纸篓。"
        )
        if removed_names:
            removed_preview = "、".join(removed_names[:5])
            if len(removed_names) > 5:
                removed_preview = f"{removed_preview} 等 {len(removed_names)} 个文件"
            self._append_log(f"已删除的本地文件：{removed_preview}")

        if failed_messages:
            failure_preview = "；".join(failed_messages[:3])
            if len(failed_messages) > 3:
                failure_preview = f"{failure_preview}；另有 {len(failed_messages) - 3} 个文件删除失败"
            self._append_log(f"部分文件删除失败：{failure_preview}")
            QMessageBox.warning(
                self,
                "部分删除成功",
                (
                    f"已删除 {len(removed_names)} 个本地重复文件，"
                    f"另有 {len(failed_messages)} 个删除失败。\n\n{failure_preview}"
                ),
            )
            return

        QMessageBox.information(
            self,
            "删除完成",
            f"已将 {len(removed_names)} 个本地重复文件移到系统回收站/废纸篓。",
        )

    def start_analysis(self) -> None:
        if self.worker and self.worker.isRunning():
            self._warn("提示", "当前已有分析任务在进行中。")
            return

        self._clear_analysis_view()
        self._refresh_target_folder_before_analysis()

        if not self.selected_files:
            self._warn("提示", "请先添加 PDF 文件后再开始分析。")
            return

        self.status_label.setText("状态：分析中")
        self.export_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._append_log(f"开始分析，共 {len(self.selected_files)} 个文件。")
        for path in self.selected_files:
            self.file_statuses[self._path_key(path)] = "排队中"
        self._refresh_file_queue()
        self._refresh_button_states()

        options = {
            "ocr_enabled": bool(self.config.get("ocr_enabled", True)),
            "ocr_confidence_threshold": float(self.config.get("ocr_confidence_threshold", 0.75)),
            "max_preview_text_chars": int(self.config.get("max_preview_text_chars", 1200)),
            "invoice_title_source": str(self.config.get("invoice_title_source", "filename")),
        }
        self.worker = AnalysisWorker(self.selected_files[:], options)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_emitted.connect(self._append_log)
        self.worker.finished_with_results.connect(self._on_analysis_finished)
        self.worker.failed.connect(self._on_analysis_failed)
        self.worker.start()

    def export_excel(self) -> None:
        if not self.analysis_completed:
            self._warn("提示", "请先完成分析，再执行导出。")
            return
        if not self.records:
            self._warn("提示", "当前没有可导出的结果。")
            return

        output_path = self.output_path
        if not output_path:
            output_path = self._initial_output_path()
            self.output_path = output_path
            self.output_path_label.setText(f"输出路径：{self.output_path}")
            self._append_log(f"未设置输出路径，已自动使用默认路径：{output_path}")

        try:
            current_signature = self._current_records_signature()
            if self._should_create_followup_export(output_path, current_signature):
                output_path = self._build_unique_export_path(output_path)
                self.output_path = output_path
                self.output_path_label.setText(f"输出路径：{self.output_path}")
                self._append_log(
                    f"检测到导出后结果已变化，已自动生成新的输出文件：{output_path}"
                )

            exported_path = self.exporter.export(
                self.records,
                output_path=output_path,
                template_path=None,
            )
            self.output_path = exported_path
            self.output_path_label.setText(f"输出路径：{self.output_path}")
            self.last_exported_path = exported_path
            self.last_export_signature = current_signature
            self.status_label.setText("状态：导出完成")
            self._append_log(f"Excel 导出成功：{exported_path}")
            QMessageBox.information(
                self,
                "Excel 已生成完成",
                f"Excel 已成功生成：\n{exported_path}",
            )
        except Exception as exc:
            logger.exception("Export failed")
            QMessageBox.critical(
                self,
                "Excel 生成失败",
                f"生成 Excel 失败：\n{exc}",
            )
            self._append_log(f"Excel 导出失败：{exc}")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            pdf_urls = [
                url for url in event.mimeData().urls() if is_pdf_file(Path(url.toLocalFile()))
            ]
            if pdf_urls:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        file_paths = []
        for url in event.mimeData().urls():
            local_path = Path(url.toLocalFile())
            if is_pdf_file(local_path):
                file_paths.append(local_path)

        if file_paths:
            self._add_files(file_paths)
            event.acceptProposedAction()
        else:
            self._warn("提示", "拖拽内容中未检测到 PDF 文件。")

    def _add_files(self, file_paths: list[Path]) -> None:
        existing = {path.resolve() for path in self.selected_files}
        added_count = 0
        duplicate_count = 0

        for path in file_paths:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path

            if not is_pdf_file(path):
                self._append_log(f"已跳过非 PDF 文件：{path}")
                continue
            if resolved in existing:
                duplicate_count += 1
                self._append_log(f"已跳过重复文件：{path.name}")
                continue
            self.selected_files.append(path)
            existing.add(resolved)
            added_count += 1

        if added_count:
            self.analysis_completed = False
            self.records = []
            self.table.setRowCount(0)
            self._update_total_amount_label([])
            self._append_log(f"新增文件 {added_count} 个。")
        if duplicate_count:
            self._append_log(f"发现重复导入文件 {duplicate_count} 个，已跳过。")

        self.file_count_label.setText(f"当前文件：{len(self.selected_files)}")
        self._refresh_file_queue()
        self._refresh_button_states()

    def _on_progress_changed(self, current: int, total: int, message: str) -> None:
        percentage = 0 if total == 0 else int(current / total * 100)
        self.progress_bar.setValue(min(percentage, 100))
        self.status_label.setText(f"状态：{message}")
        prefix = "正在处理："
        if message.startswith(prefix):
            current_name = message.removeprefix(prefix).strip()
            for path in self.selected_files:
                key = self._path_key(path)
                if path.name == current_name:
                    self.file_statuses[key] = "分析中"
                elif self.file_statuses.get(key) == "分析中":
                    self.file_statuses[key] = "排队中"
            self._refresh_file_queue()

    def _on_analysis_finished(self, records: list[InvoiceRecord]) -> None:
        self.worker = None
        self.records = records
        self.analysis_completed = True
        self.progress_bar.setValue(100)
        self.status_label.setText("状态：分析完成")
        self._populate_table(records)
        self._update_total_amount_label(records)
        self._apply_record_statuses(records)
        self._refresh_button_states()

        if not records:
            self._warn("提示", "分析完成，但没有生成任何结果。")
            return

        failed_count = sum(1 for item in records if not item.parse_success)
        success_count = len(records) - failed_count
        self._append_log(f"分析结束：成功 {success_count} 条，失败 {failed_count} 条。")
        QMessageBox.information(
            self,
            "分析完成",
            f"已完成 {len(records)} 个文件的分析。\n成功：{success_count}\n失败：{failed_count}",
        )

    def _on_analysis_failed(self, message: str) -> None:
        self.worker = None
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：分析失败")
        self.analysis_completed = False
        self._update_total_amount_label([])
        for path in self.selected_files:
            self.file_statuses[self._path_key(path)] = "分析失败"
        self._refresh_file_queue()
        self._refresh_button_states()
        self._warn("分析失败", message)
        self._append_log(f"分析失败：{message}")

    def _populate_table(self, records: list[InvoiceRecord]) -> None:
        self.table.setRowCount(0)
        for row_index, record in enumerate(records):
            self.table.insertRow(row_index)
            values = [
                str(record.index),
                record.file_name,
                record.invoice_number,
                "" if record.total_amount is None else f"{record.total_amount:.2f}",
                record.invoice_date,
                record.seller_name,
                record.buyer_name,
                record.item_name,
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column_index in (0, 2, 3, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row_index, column_index, item)

    def _refresh_file_queue(self) -> None:
        self.file_list_widget.clear()
        self.queue_count_label.setText(f"数量：{len(self.selected_files)}")
        for path in self.selected_files:
            status = self.file_statuses.get(self._path_key(path), "待分析")
            item = QListWidgetItem(f"[{status}] {path.name}")
            item.setToolTip(str(path))
            self.file_list_widget.addItem(item)

    def _apply_record_statuses(self, records: list[InvoiceRecord]) -> None:
        for record in records:
            status = "已完成"
            if self._needs_review(record):
                status = "需复核"
            self.file_statuses[self._path_key(record.file_path)] = status
        self._refresh_file_queue()

    def _update_total_amount_label(self, records: list[InvoiceRecord]) -> None:
        total_amount = sum(record.total_amount or 0 for record in records)
        duplicate_count = self._count_duplicate_groups(records)
        self.total_amount_label.setText(f"总金额：{total_amount:.2f} 元")
        self.duplicate_count_label.setText(f"重复组数：{duplicate_count}")

    def _needs_review(self, record: InvoiceRecord) -> bool:
        review_tokens = ("缺少", "失败", "疑似重复", "OCR 置信度偏低")
        return any(token in record.remarks for token in review_tokens)

    def _is_duplicate_record(self, record: InvoiceRecord) -> bool:
        return bool(record.duplicate_invoice or record.duplicate_file)

    def _count_duplicate_groups(self, records: list[InvoiceRecord]) -> int:
        duplicate_groups: set[str] = set()
        for record in records:
            if record.duplicate_invoice and record.invoice_number:
                duplicate_groups.add(f"invoice:{record.invoice_number.strip()}")
                continue

            if record.duplicate_file and record.file_hash:
                duplicate_groups.add(f"file:{record.file_hash}")

        return len(duplicate_groups)

    def _replace_records(self, records: list[InvoiceRecord]) -> None:
        for index, record in enumerate(records, start=1):
            record.index = index

        InvoiceBatchProcessor.refresh_duplicate_annotations(records)

        self.records = records
        self.selected_files = [record.file_path for record in records]
        self.file_statuses = {}
        self.file_count_label.setText(f"当前文件：{len(self.selected_files)}")
        self._populate_table(self.records)
        self._update_total_amount_label(self.records)
        self._apply_record_statuses(self.records)
        self._refresh_button_states()

    def _clear_analysis_view(self) -> None:
        self.records = []
        self.analysis_completed = False
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：待命")
        self._update_total_amount_label([])
        self.file_statuses.clear()
        self._refresh_file_queue()

    def _refresh_target_folder_before_analysis(self) -> None:
        if self.target_folder is None:
            return

        folder_path = self.target_folder
        if not folder_path.exists():
            self._append_log(f"目标文件夹不存在，已跳过刷新：{folder_path}")
            self._set_target_folder_files([])
            self.target_folder = None
            self.target_folder_files.clear()
            return

        file_paths = sorted(
            [path for path in folder_path.rglob("*") if is_pdf_file(path)],
            key=lambda item: item.name.lower(),
        )
        previous_keys = {self._path_key(path) for path in self.target_folder_files}
        self._set_target_folder_files(file_paths)
        refreshed_keys = {self._path_key(path) for path in self.target_folder_files}
        if refreshed_keys != previous_keys:
            self._append_log(
                f"已刷新目标文件夹：{folder_path}，当前待处理文件 {len(self.selected_files)} 个。"
            )

    def _set_target_folder_files(self, file_paths: list[Path]) -> None:
        previous_folder_keys = {self._path_key(path) for path in self.target_folder_files}
        manual_files = [
            path for path in self.selected_files if self._path_key(path) not in previous_folder_keys
        ]

        merged_files: list[Path] = []
        seen_keys: set[str] = set()
        for path in [*file_paths, *manual_files]:
            key = self._path_key(path)
            if key in seen_keys:
                continue
            merged_files.append(path)
            seen_keys.add(key)

        self.target_folder_files = file_paths[:]
        self.selected_files = merged_files
        self.file_count_label.setText(f"当前文件：{len(self.selected_files)}")

    def _build_local_delete_detail_text(self, duplicate_records: list[InvoiceRecord]) -> str:
        if not duplicate_records:
            return "当前没有可删除的本地重复文件。"

        lines: list[str] = []
        for index, record in enumerate(duplicate_records, start=1):
            lines.append(f"{index}. {record.file_name}")
            lines.append(f"   路径：{record.file_path}")
        return "\n".join(lines)

    def _current_records_signature(self) -> tuple:
        return tuple(
            (
                record.index,
                str(record.file_path),
                record.file_hash,
                record.invoice_number,
                record.total_amount,
                record.invoice_date,
                record.seller_name,
                record.buyer_name,
                record.item_name,
                record.remarks,
            )
            for record in self.records
        )

    def _should_create_followup_export(
        self,
        output_path: Path,
        current_signature: tuple,
    ) -> bool:
        if self.last_exported_path is None or self.last_export_signature is None:
            return False

        return (
            self._path_key(output_path) == self._path_key(self.last_exported_path)
            and current_signature != self.last_export_signature
        )

    def _build_unique_export_path(self, output_path: Path) -> Path:
        suffix = output_path.suffix or ".xlsx"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = output_path.with_name(f"{output_path.stem}_{timestamp}{suffix}")
        counter = 2
        while candidate.exists():
            candidate = output_path.with_name(
                f"{output_path.stem}_{timestamp}_{counter}{suffix}"
            )
            counter += 1
        return candidate

    def _move_file_to_trash(self, path: Path) -> tuple[bool, str]:
        try:
            result = QFile.moveToTrash(str(path))
        except Exception as exc:
            logger.exception("Failed to move file to trash: %s", path)
            return False, str(exc)

        if isinstance(result, tuple):
            success = bool(result[0])
            detail = str(result[1]) if len(result) > 1 and result[1] else ""
        else:
            success = bool(result)
            detail = ""

        if not success:
            return False, detail or "系统未返回可用的删除结果"

        return True, detail

    def _path_key(self, path: Path) -> str:
        try:
            return str(path.resolve())
        except OSError:
            return str(path)

    def _refresh_button_states(self) -> None:
        has_files = bool(self.selected_files)
        running = bool(self.worker and self.worker.isRunning())
        self.start_button.setEnabled(has_files and not running)
        self.export_button.setEnabled(self.analysis_completed and bool(self.records) and not running)
        duplicate_file_groups = (
            InvoiceBatchProcessor.count_duplicate_file_groups(self.records)
            if self.analysis_completed and self.records
            else 0
        )
        self.remove_duplicates_button.setEnabled(
            self.analysis_completed and duplicate_file_groups > 0 and not running
        )
        self.delete_local_duplicates_button.setEnabled(
            self.analysis_completed and duplicate_file_groups > 0 and not running
        )
        self.clear_button.setEnabled(not running)
        self.folder_button.setEnabled(not running)
        self.output_button.setEnabled(not running)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] {message}")

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _initial_output_path(self) -> Path:
        saved_dir = self.config.get("default_output_dir", "")
        base_dir = Path(saved_dir) if saved_dir else desktop_dir()
        filename = f"发票汇总_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return base_dir / filename

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f3f5f7;
            }
            QFrame#TopPanel, QFrame#QueuePanel, QFrame#ResultsPanel, QFrame#BottomPanel {
                background: white;
                border: 1px solid #d9e0e6;
                border-radius: 10px;
            }
            QLabel#SectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #1f2937;
            }
            QLabel#AmountSummary {
                font-size: 14px;
                font-weight: 600;
                color: #3d6f8e;
            }
            QLabel#HintLabel {
                color: #6b7280;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 14px;
                border-radius: 6px;
                border: 1px solid #b8c4d0;
                background: #f8fafc;
            }
            QPushButton:hover {
                background: #eef4f8;
            }
            QPushButton#PrimaryActionButton {
                font-weight: 700;
                color: #1f3442;
                background: #e7f0f6;
                border: 2px solid #6a8496;
            }
            QPushButton#PrimaryActionButton:hover {
                background: #dceaf2;
                border-color: #567183;
            }
            QPushButton#HeaderActionButton {
                font-weight: 600;
                color: #274151;
                background: #f8fafc;
                border: 2px solid #6a8496;
            }
            QPushButton#HeaderActionButton:hover {
                background: #eef4f8;
                border-color: #567183;
            }
            QPushButton#DangerActionButton {
                font-weight: 600;
                color: #7d2d2f;
                background: #fff4f2;
                border: 2px solid #dba6a3;
            }
            QPushButton#DangerActionButton:hover {
                background: #fde8e5;
                border-color: #c88986;
            }
            QPushButton:disabled {
                color: #9aa6b2;
                background: #f4f4f4;
                border-color: #d6dce1;
            }
            QTableWidget {
                gridline-color: #e5e7eb;
                background: white;
                alternate-background-color: #f8fbfd;
            }
            QHeaderView::section {
                background: #e9eff5;
                padding: 6px;
                border: 0;
                border-right: 1px solid #dce3ea;
                border-bottom: 1px solid #dce3ea;
                font-weight: 600;
            }
            QTextEdit {
                background: #fbfcfd;
                border: 1px solid #d9e0e6;
                border-radius: 8px;
            }
            QListWidget {
                background: #fbfcfd;
                border: 1px solid #d9e0e6;
                border-radius: 8px;
                padding: 4px;
            }
            QProgressBar {
                min-height: 22px;
                border: 1px solid #c7d2da;
                border-radius: 6px;
                background: #f6f8fa;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #3d6f8e;
                border-radius: 5px;
            }
            """
        )
