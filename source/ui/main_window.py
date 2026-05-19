from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from qt_compat import (
    QAbstractItemView,
    QColor,
    QDesktopServices,
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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    Qt,
    QUrl,
    QVBoxLayout,
    QWidget,
)

from exporters.excel_exporter import ExcelExporter
from models.invoice_record import InvoiceRecord
from services.file_selection_service import discover_pdf_files
from services.invoice_service import InvoiceBatchProcessor
from ui.workers import AnalysisWorker
from utils.config import AppConfig
from utils.constants import PREVIEW_HEADERS
from utils.file_utils import desktop_dir, is_pdf_file, validate_pdf_file
from utils.logging_utils import safe_log_path

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
        self.active_result_filter = "all"
        self.filter_buttons: dict[str, QPushButton] = {}
        self.worker: AnalysisWorker | None = None
        self.last_exported_path: Path | None = None
        self.last_export_signature: tuple | None = None

        self.setWindowTitle("PDF发票自动整理归纳工具")
        self.setMinimumSize(1280, 820)
        self.setAcceptDrops(True)

        self.output_path = self._initial_output_path()
        self._build_ui()
        self._refresh_button_states()
        self._append_log("软件已启动，可添加 PDF 文件开始使用。")

    def _build_ui(self) -> None:
        self.page_stack = QStackedWidget()
        self.main_page = QWidget()
        root_layout = QVBoxLayout(self.main_page)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(8)

        top_panel = self._build_top_panel()
        queue_panel = self._build_queue_panel()
        results_panel = self._build_results_panel()
        self.log_page = self._build_log_page()

        queue_panel.setFixedHeight(165)
        results_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        root_layout.addWidget(top_panel)
        root_layout.addWidget(queue_panel)
        root_layout.addWidget(results_panel, 1)

        self.page_stack.addWidget(self.main_page)
        self.page_stack.addWidget(self.log_page)
        self.setCentralWidget(self.page_stack)
        self._apply_styles()

    def _build_top_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("TopPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        file_card = QFrame()
        file_card.setObjectName("TopActionCard")
        file_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(0, 10, 12, 10)
        file_layout.setSpacing(8)

        file_title_row = QHBoxLayout()
        file_title_row.setSpacing(8)
        file_title = QLabel("文件与导出")
        file_title.setObjectName("SectionTitle")
        file_title_row.addWidget(file_title)
        file_title_row.addStretch(1)
        file_layout.addLayout(file_title_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.file_button = QPushButton("选择 PDF 文件")
        self._configure_toolbar_button(self.file_button, minimum_width=150)
        self.file_button.clicked.connect(self.choose_files)
        button_row.addWidget(self.file_button)

        self.folder_button = QPushButton("选择文件夹")
        self._configure_toolbar_button(self.folder_button, minimum_width=132)
        self.folder_button.clicked.connect(self.choose_folder)
        button_row.addWidget(self.folder_button)

        self.output_button = QPushButton("更改导出位置")
        self._configure_toolbar_button(self.output_button, minimum_width=150)
        self.output_button.clicked.connect(self.choose_output_path)
        button_row.addWidget(self.output_button)
        button_row.addStretch(1)
        file_layout.addLayout(button_row)

        self.output_path_label = QLabel(f"输出路径：{self.output_path}")
        self.output_path_label.setObjectName("PathLabel")
        self.output_path_label.setWordWrap(True)
        file_layout.addWidget(self.output_path_label)

        hint = QLabel("可选择 PDF 文件、选择文件夹，或直接把 PDF 文件拖拽到窗口中。")
        hint.setObjectName("HintLabel")
        file_layout.addWidget(hint)

        status_card = QFrame()
        status_card.setObjectName("TopStatusCard")
        status_card.setMinimumWidth(430)
        status_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(0, 10, 12, 10)
        status_layout.setSpacing(8)

        status_title_row = QHBoxLayout()
        status_title_row.setSpacing(8)
        status_title = QLabel("处理状态")
        status_title.setObjectName("SectionTitle")
        status_title_row.addWidget(status_title)
        status_title_row.addStretch(1)

        self.log_page_button = QPushButton("日志 / 状态")
        self.log_page_button.setObjectName("HeaderActionButton")
        self.log_page_button.setToolTip("查看详细运行日志和状态记录")
        self._configure_toolbar_button(self.log_page_button, minimum_width=104)
        self.log_page_button.clicked.connect(self._show_log_page)
        status_title_row.addWidget(self.log_page_button)
        status_layout.addLayout(status_title_row)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(8)

        self.file_count_label = QLabel("当前文件：0")
        self.file_count_label.setObjectName("TopMetricLabel")
        self.file_count_label.setMinimumWidth(118)
        metric_row.addWidget(self.file_count_label)

        self.status_label = QLabel("状态：待命")
        self.status_label.setObjectName("TopMetricLabel")
        self.status_label.setMinimumWidth(178)
        self.status_label.setWordWrap(True)
        metric_row.addWidget(self.status_label, 1)

        status_layout.addLayout(metric_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumWidth(260)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        status_layout.addWidget(self.progress_bar)

        layout.addWidget(file_card, 3)
        layout.addWidget(status_card, 2)
        return panel

    def _build_results_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("ResultsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)

        title = QLabel("解析结果预览")
        title.setObjectName("SectionTitle")
        summary_row.addWidget(title)

        self.total_amount_label = QLabel("总金额：全部 0.00 / 去重 0.00 元")
        self.total_amount_label.setObjectName("SummaryBadge")
        self.total_amount_label.setMinimumWidth(340)
        summary_row.addWidget(self.total_amount_label)

        self.duplicate_count_label = QLabel("相同文件：0 组 / 相同票号：0 组")
        self.duplicate_count_label.setObjectName("SummaryBadge")
        self.duplicate_count_label.setMinimumWidth(300)
        summary_row.addWidget(self.duplicate_count_label)

        summary_row.addStretch(1)
        layout.addLayout(summary_row)

        layout.addWidget(self._build_results_controls_panel())

        self.table = QTableWidget(0, len(PREVIEW_HEADERS))
        self.table.setHorizontalHeaderLabels(PREVIEW_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumSectionSize(72)
        default_widths = [70, 220, 100, 180, 120, 110, 220, 220, 260, 360]
        for column, width in enumerate(default_widths):
            self.table.setColumnWidth(column, width)
        self.table.cellDoubleClicked.connect(self.show_record_detail)
        layout.addWidget(self.table, 1)
        return panel

    def _build_results_controls_panel(self) -> QWidget:
        controls_panel = QFrame()
        controls_panel.setObjectName("ResultsControlsPanel")
        controls_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        controls_row = QHBoxLayout(controls_panel)
        controls_row.setContentsMargins(8, 8, 8, 8)
        controls_row.setSpacing(8)

        self.start_button = QPushButton("开始分析")
        self.start_button.setObjectName("PrimaryActionButton")
        self._configure_toolbar_button(self.start_button, minimum_width=94)
        self.start_button.clicked.connect(self.start_analysis)

        self.cancel_button = QPushButton("取消分析")
        self.cancel_button.setObjectName("HeaderActionButton")
        self._configure_toolbar_button(self.cancel_button, minimum_width=94)
        self.cancel_button.clicked.connect(self.cancel_analysis)

        self.remove_duplicates_button = QPushButton("移除重复项")
        self.remove_duplicates_button.setObjectName("HeaderActionButton")
        self.remove_duplicates_button.setToolTip("只从结果表移除重复项，不删除本地 PDF 文件。")
        self._configure_toolbar_button(self.remove_duplicates_button, minimum_width=120)
        self.remove_duplicates_button.clicked.connect(self.remove_duplicate_files)

        self.delete_local_duplicates_button = QPushButton("移到废纸篓")
        self.delete_local_duplicates_button.setObjectName("DangerActionButton")
        self.delete_local_duplicates_button.setToolTip("把本地重复 PDF 移到系统废纸篓/回收站。")
        self._configure_toolbar_button(self.delete_local_duplicates_button, minimum_width=112)
        self.delete_local_duplicates_button.clicked.connect(self.delete_duplicate_local_files)

        self.export_button = QPushButton("输出 Excel")
        self.export_button.setObjectName("PrimaryActionButton")
        self._configure_toolbar_button(self.export_button, minimum_width=112)
        self.export_button.clicked.connect(self.export_excel)

        self.clear_button = QPushButton("清空列表")
        self.clear_button.setObjectName("HeaderActionButton")
        self._configure_toolbar_button(self.clear_button, minimum_width=90)
        self.clear_button.clicked.connect(self.clear_files)

        filter_specs = [
            ("all", "全部"),
            ("failed", "失败"),
            ("review", "复核"),
            ("duplicate", "重复"),
        ]
        filter_widgets: list[QWidget] = []
        for filter_name, label in filter_specs:
            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setCheckable(True)
            self._configure_toolbar_button(button, minimum_width=64)
            button.clicked.connect(lambda checked=False, name=filter_name: self._set_result_filter(name))
            self.filter_buttons[filter_name] = button
            filter_widgets.append(button)

        self.filter_status_label = QLabel("显示 0 / 0")
        self.filter_status_label.setObjectName("FilterStatusLabel")
        self.filter_status_label.setMinimumWidth(118)
        self.filter_status_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        filter_widgets.append(self.filter_status_label)
        self._refresh_filter_buttons()

        controls_row.addWidget(
            self._build_control_group(
                "分析",
                [self.start_button, self.cancel_button],
                minimum_width=220,
            ),
            2,
        )
        controls_row.addWidget(
            self._build_control_group(
                "筛选显示",
                filter_widgets,
                minimum_width=430,
            ),
            5,
        )
        controls_row.addWidget(
            self._build_control_group(
                "重复处理",
                [self.remove_duplicates_button, self.delete_local_duplicates_button],
                minimum_width=270,
            ),
            3,
        )
        controls_row.addWidget(
            self._build_control_group(
                "导出",
                [self.export_button, self.clear_button],
                minimum_width=220,
            ),
            2,
        )

        return controls_panel

    def _build_control_group(
        self,
        title: str,
        widgets: list[QWidget],
        *,
        minimum_width: int,
    ) -> QWidget:
        group = QFrame()
        group.setObjectName("ControlGroup")
        group.setMinimumWidth(minimum_width)
        group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(8, 6, 8, 8)
        group_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("ControlGroupTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(title_label)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        controls.addStretch(1)
        for widget in widgets:
            controls.addWidget(widget)
        controls.addStretch(1)
        group_layout.addLayout(controls)
        return group

    def _build_queue_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("QueuePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 8, 14, 8)
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
        self.file_list_widget.setFixedHeight(112)
        self.file_list_widget.setUniformItemSizes(True)
        self.file_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.file_list_widget)
        return panel

    def _build_log_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header_panel = QFrame()
        header_panel.setObjectName("LogHeaderPanel")
        header_layout = QHBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(10)

        self.back_to_main_button = QPushButton("返回主界面")
        self.back_to_main_button.setObjectName("HeaderActionButton")
        self._configure_toolbar_button(self.back_to_main_button, minimum_width=118)
        self.back_to_main_button.clicked.connect(self._show_main_page)
        header_layout.addWidget(self.back_to_main_button)

        title = QLabel("日志 / 状态")
        title.setObjectName("SectionTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self.log_file_summary_label = QLabel("当前文件：0")
        self.log_file_summary_label.setObjectName("SummaryBadge")
        self.log_file_summary_label.setMinimumWidth(120)
        header_layout.addWidget(self.log_file_summary_label)

        self.log_status_summary_label = QLabel("状态：待命")
        self.log_status_summary_label.setObjectName("SummaryBadge")
        self.log_status_summary_label.setMinimumWidth(220)
        header_layout.addWidget(self.log_status_summary_label)

        layout.addWidget(header_panel)

        content_panel = QFrame()
        content_panel.setObjectName("LogContentPanel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(14, 12, 14, 14)
        content_layout.setSpacing(8)

        intro_row = QHBoxLayout()
        intro_row.setSpacing(8)

        intro = QLabel("这里显示程序运行、识别、导出和异常提示的详细记录；主界面默认隐藏这些细节。")
        intro.setObjectName("HintLabel")
        intro_row.addWidget(intro)

        intro_row.addStretch(1)

        self.log_count_label = QLabel("日志条数：0")
        self.log_count_label.setObjectName("HintLabel")
        intro_row.addWidget(self.log_count_label)
        content_layout.addLayout(intro_row)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content_layout.addWidget(self.log_box, 1)

        layout.addWidget(content_panel, 1)
        return page

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
        discovery = discover_pdf_files(folder_path)
        file_paths = discovery.files
        if not file_paths:
            self._warn("提示", "所选文件夹中未找到 PDF 文件。")
            return
        self._append_discovery_messages(discovery.skipped, discovery.errors)

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

        if self.selected_files or self.records:
            message = "将清空当前文件列表和识别结果，不会删除本地 PDF 文件。"
            if self.records and self.last_export_signature != self._current_records_signature():
                message += "\n\n当前识别结果可能尚未导出。"
            reply = QMessageBox.question(
                self,
                "确认清空列表",
                f"{message}\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.selected_files.clear()
        self.target_folder = None
        self.target_folder_files.clear()
        self.file_statuses.clear()
        self.records.clear()
        self.analysis_completed = False
        self.table.setRowCount(0)
        self._apply_result_filter()
        self.progress_bar.setValue(0)
        self._set_status("状态：待命")
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
            "从结果中移除重复项",
            (
                f"检测到 {duplicate_group_count} 组相同 PDF 内容，"
                f"将从当前结果中移除 {duplicate_remove_count} 个重复项，"
                "每组仅保留第一份。\n\n"
                "此操作不会删除本地 PDF 原文件。\n\n是否继续？"
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
            f"已从结果中移除 {duplicate_remove_count} 个重复项，保留 {len(kept_records)} 个文件。本地 PDF 未删除。"
        )
        if preview_names:
            self._append_log(f"已移除的文件：{preview_names}")

        QMessageBox.information(
            self,
            "移除完成",
            f"已从结果中移除 {duplicate_remove_count} 个重复项，当前保留 {len(kept_records)} 个文件。\n本地 PDF 原文件未删除。",
        )

    def delete_duplicate_local_files(self) -> None:
        if not self.analysis_completed or not self.records:
            self._warn("提示", "请先完成分析，再移动本地重复文件。")
            return

        duplicate_group_count = InvoiceBatchProcessor.count_duplicate_file_groups(self.records)
        _, duplicate_records = InvoiceBatchProcessor.split_duplicate_file_records(self.records)
        duplicate_remove_count = len(duplicate_records)
        if duplicate_remove_count <= 0:
            self._warn("提示", "当前没有可移动的本地重复文件。")
            return

        if self.records and self.last_export_signature != self._current_records_signature():
            reply = QMessageBox.question(
                self,
                "建议先导出备份",
                (
                    "当前识别结果可能尚未导出。建议先导出 Excel 作为备份，"
                    "再移动本地 PDF 文件。\n\n是否仍要继续移动本地重复文件？"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.setWindowTitle("移动本地重复文件")
        message_box.setText(
            (
                f"检测到 {duplicate_group_count} 组相同 PDF 内容，"
                f"将把 {duplicate_remove_count} 个本地重复文件移到系统回收站/废纸篓，"
                "每组仅保留第一份。此操作会移动实际本地 PDF 原文件，不只是从列表移除。"
            )
        )
        message_box.setInformativeText(
            "该操作会同时把这些文件从当前分析结果中移除。展开“显示详情”可查看完整文件清单。"
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
            error_preview = "；".join(failed_messages[:3]) if failed_messages else "没有文件被移动。"
            self._warn("移动失败", error_preview)
            self._append_log(f"移动本地重复文件失败：{error_preview}")
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
            self._append_log(f"已移动到废纸篓/回收站的本地文件：{removed_preview}")

        if failed_messages:
            failure_preview = "；".join(failed_messages[:3])
            if len(failed_messages) > 3:
                failure_preview = f"{failure_preview}；另有 {len(failed_messages) - 3} 个文件移动失败"
            self._append_log(f"部分文件移动失败：{failure_preview}")
            QMessageBox.warning(
                self,
                "部分移动成功",
                (
                    f"已移动 {len(removed_names)} 个本地重复文件，"
                    f"另有 {len(failed_messages)} 个移动失败。\n\n{failure_preview}"
                ),
            )
            return

        QMessageBox.information(
            self,
            "移动完成",
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

        self._set_status("状态：分析中")
        self.export_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._append_log(f"开始分析，共 {len(self.selected_files)} 个文件。")
        for path in self.selected_files:
            self.file_statuses[self._path_key(path)] = "排队中"
        self._refresh_file_queue()

        options = {
            "ocr_enabled": bool(self.config.get("ocr_enabled", True)),
            "ocr_confidence_threshold": float(self.config.get("ocr_confidence_threshold", 0.75)),
            "max_preview_text_chars": int(self.config.get("max_preview_text_chars", 1200)),
            "invoice_title_source": str(self.config.get("invoice_title_source", "filename")),
            "max_ocr_pages": int(self.config.get("max_ocr_pages", 10)),
            "ocr_render_scale": float(self.config.get("ocr_render_scale", 2.0)),
            "ocr_try_variants": bool(self.config.get("ocr_try_variants", True)),
        }
        self.worker = AnalysisWorker(self.selected_files[:], options)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_emitted.connect(self._append_log)
        self.worker.finished_with_results.connect(self._on_analysis_finished)
        self.worker.cancelled_with_results.connect(self._on_analysis_cancelled)
        self.worker.failed.connect(self._on_analysis_failed)
        self.worker.start()
        self._refresh_button_states()

    def cancel_analysis(self) -> None:
        if not self.worker or not self.worker.isRunning():
            return
        self.worker.cancel()
        self.cancel_button.setEnabled(False)
        self._set_status("状态：正在取消，等待当前文件处理结束")
        self._append_log("已请求取消分析，当前文件处理结束后将停止。")

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

            output_path = self._resolve_export_output_path(output_path)
            if output_path is None:
                self._append_log("已取消 Excel 导出。")
                return

            template_path = self._configured_template_path()
            exported_path = self.exporter.export(
                self.records,
                output_path=output_path,
                template_path=template_path,
            )
            self.output_path = exported_path
            self.output_path_label.setText(f"输出路径：{self.output_path}")
            self.last_exported_path = exported_path
            self.last_export_signature = current_signature
            self._set_status("状态：导出完成")
            self._append_log(f"Excel 导出成功：{exported_path}（{len(self.records)} 条）")
            self._confirm_open_exported_file(exported_path)
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
        existing = {Path(self._path_key(path)) for path in self.selected_files}
        added_count = 0
        duplicate_count = 0
        invalid_count = 0

        for path in file_paths:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path

            valid, reason = validate_pdf_file(path)
            if not valid:
                invalid_count += 1
                self._append_log(f"已跳过无效 PDF：{path.name}（{reason}）")
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
            self._apply_result_filter()
            self._update_total_amount_label([])
            self._append_log(f"新增文件 {added_count} 个。")
        if duplicate_count:
            self._append_log(f"发现重复导入文件 {duplicate_count} 个，已跳过。")
        if invalid_count:
            self._append_log(f"发现无效或不支持的 PDF {invalid_count} 个，已跳过。")

        self.file_count_label.setText(f"当前文件：{len(self.selected_files)}")
        self._refresh_file_queue()
        self._refresh_button_states()

    def _on_progress_changed(self, current: int, total: int, message: str) -> None:
        percentage = 0 if total == 0 else int(current / total * 100)
        self.progress_bar.setValue(min(percentage, 100))
        self._set_status(f"状态：{message}")
        if message.startswith("正在识别") and "：" in message:
            current_name = message.rsplit("：", 1)[-1].strip()
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
        self._set_status("状态：分析完成")
        self._populate_table(records)
        self._update_total_amount_label(records)
        self._apply_record_statuses(records)
        self._refresh_button_states()

        if not records:
            self._warn("提示", "分析完成，但没有生成任何结果。")
            return

        failed_count = sum(1 for item in records if not item.parse_success)
        success_count = len(records) - failed_count
        review_count = sum(1 for item in records if self._needs_review(item) or self._is_duplicate_record(item))
        self._append_log(
            f"分析结束：核心字段完整 {success_count} 条，失败 {failed_count} 条，需复核 {review_count} 条。"
        )

    def _on_analysis_cancelled(self, records: list[InvoiceRecord]) -> None:
        self.worker = None
        self.records = records
        self.analysis_completed = bool(records)
        self._set_status("状态：分析已取消")
        self._populate_table(records)
        self._update_total_amount_label(records)
        self._apply_record_statuses(records)
        for path in self.selected_files:
            key = self._path_key(path)
            if key not in self.file_statuses:
                self.file_statuses[key] = "未处理"
            elif self.file_statuses[key] in ("排队中", "分析中"):
                self.file_statuses[key] = "未处理"
        self._refresh_file_queue()
        self._refresh_button_states()

        processed_count = len(records)
        remaining_count = max(len(self.selected_files) - processed_count, 0)
        self._append_log(
            f"分析已取消：已处理 {processed_count} 个，未处理 {remaining_count} 个。"
        )
        QMessageBox.information(
            self,
            "分析已取消",
            (
                f"已处理：{processed_count} 个\n"
                f"未处理：{remaining_count} 个\n\n"
                "已处理结果仍保留，可导出已完成部分，或重新开始分析。"
            ),
        )

    def _on_analysis_failed(self, message: str) -> None:
        self.worker = None
        self.progress_bar.setValue(0)
        self._set_status("状态：分析失败")
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
            background_color = self._row_background_color(record)
            values = [
                str(record.index),
                record.file_name,
                self._record_status_label(record),
                record.invoice_number,
                "" if record.total_amount is None else f"{record.total_amount:.2f}",
                record.invoice_date,
                record.seller_name,
                record.buyer_name,
                record.item_name,
                record.remarks,
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setForeground(self._table_item_foreground(record, column_index))
                if background_color is not None:
                    item.setBackground(background_color)
                if column_index in (0, 2, 3, 4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row_index, column_index, item)
            self.table.setRowHeight(row_index, 28)
        self._apply_result_filter()

    def _set_result_filter(self, filter_name: str) -> None:
        self.active_result_filter = filter_name
        self._refresh_filter_buttons()
        self._apply_result_filter()

    def _refresh_filter_buttons(self) -> None:
        for filter_name, button in self.filter_buttons.items():
            button.setChecked(filter_name == self.active_result_filter)

    def _apply_result_filter(self) -> None:
        visible_count = 0
        for row_index, record in enumerate(self.records):
            visible = self._record_matches_filter(record)
            self.table.setRowHidden(row_index, not visible)
            if visible:
                visible_count += 1
        if hasattr(self, "filter_status_label"):
            self.filter_status_label.setText(f"显示 {visible_count} / {len(self.records)}")

    def _record_matches_filter(self, record: InvoiceRecord) -> bool:
        if self.active_result_filter == "failed":
            return not record.parse_success
        if self.active_result_filter == "review":
            return record.parse_success and self._needs_review(record)
        if self.active_result_filter == "duplicate":
            return self._is_duplicate_record(record)
        return True

    def _row_background_color(self, record: InvoiceRecord):
        if record.duplicate_invoice_conflict:
            return QColor("#FEE2E2")
        if not record.parse_success:
            return QColor("#FEECEC")
        if record.duplicate_file or record.duplicate_invoice:
            return QColor("#FEF3C7")
        if self._needs_review(record):
            return QColor("#FEF9C3")
        return None

    def _table_item_foreground(self, record: InvoiceRecord, column_index: int) -> QColor:
        if column_index != 2:
            return QColor("#111827")
        if record.duplicate_invoice_conflict or not record.parse_success:
            return QColor("#991B1B")
        if record.duplicate_file or record.duplicate_invoice:
            return QColor("#92400E")
        if self._needs_review(record):
            return QColor("#854D0E")
        return QColor("#166534")

    def show_record_detail(self, row_index: int, column_index: int = 0) -> None:
        if row_index < 0 or row_index >= len(self.records):
            return
        record = self.records[row_index]
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowTitle("发票详情")
        message_box.setText(f"{record.file_name}\n状态：{self._record_status_label(record)}")
        message_box.setInformativeText(
            "\n".join(
                [
                    f"发票号码：{record.invoice_number or '未识别'}",
                    f"金额：{record.total_amount if record.total_amount is not None else '未识别'}",
                    f"开票日期：{record.invoice_date or '未识别'}",
                    f"销售方：{record.seller_name or '未识别'}",
                    f"购买方：{record.buyer_name or '未识别'}",
                    f"OCR：{'已使用' if record.ocr_used else '未使用'}",
                    f"OCR 置信度：{record.ocr_confidence if record.ocr_confidence is not None else '无'}",
                    f"备注：{record.remarks or '无'}",
                ]
            )
        )
        detail_lines = [
            f"文件路径：{record.file_path}",
            f"文件指纹：{record.file_hash or '无'}",
            "",
            "项目名称：",
            record.item_name or "未识别",
            "",
            "原文预览：",
            record.raw_text_preview or "无",
        ]
        message_box.setDetailedText("\n".join(detail_lines))
        message_box.exec()

    def _refresh_file_queue(self) -> None:
        self.file_list_widget.clear()
        self.queue_count_label.setText(f"数量：{len(self.selected_files)}")
        self._sync_log_page_summary()
        for path in self.selected_files:
            status = self.file_statuses.get(self._path_key(path), "待分析")
            item = QListWidgetItem(f"[{status}] {path.name}")
            item.setToolTip(str(path))
            self.file_list_widget.addItem(item)

    def _apply_record_statuses(self, records: list[InvoiceRecord]) -> None:
        for record in records:
            status = "已完成"
            if not record.parse_success:
                status = "失败"
            elif self._needs_review(record) or self._is_duplicate_record(record):
                status = "需复核"
            self.file_statuses[self._path_key(record.file_path)] = status
        self._refresh_file_queue()

    def _update_total_amount_label(self, records: list[InvoiceRecord]) -> None:
        total_amount = sum(record.total_amount or 0 for record in records)
        suggested_amount = sum(
            record.total_amount or 0
            for record in records
            if record.parse_success and not self._is_duplicate_record(record)
        )
        duplicate_file_count = InvoiceBatchProcessor.count_duplicate_file_groups(records)
        duplicate_invoice_count = self._count_duplicate_invoice_groups(records)
        self.total_amount_label.setText(
            f"总金额：全部 {total_amount:.2f} / 去重 {suggested_amount:.2f} 元"
        )
        self.duplicate_count_label.setText(
            f"相同文件：{duplicate_file_count} 组 / 相同票号：{duplicate_invoice_count} 组"
        )

    def _needs_review(self, record: InvoiceRecord) -> bool:
        review_tokens = ("缺少", "失败", "疑似重复", "高风险", "异常", "不一致", "需复核", "OCR 置信度偏低")
        return any(token in record.remarks for token in review_tokens)

    def _record_status_label(self, record: InvoiceRecord) -> str:
        if record.duplicate_invoice_conflict:
            return "重复冲突"
        if record.duplicate_file:
            return "重复文件"
        if record.duplicate_invoice:
            return "疑似重复"
        if not record.parse_success:
            return "失败"
        if self._needs_review(record):
            return "需复核"
        return "成功"

    def _is_duplicate_record(self, record: InvoiceRecord) -> bool:
        return bool(record.duplicate_invoice or record.duplicate_file)

    def _count_duplicate_invoice_groups(self, records: list[InvoiceRecord]) -> int:
        duplicate_groups: set[str] = set()
        for record in records:
            if record.duplicate_invoice and record.invoice_number:
                duplicate_groups.add(record.invoice_number.strip())
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
        self._apply_result_filter()
        self.progress_bar.setValue(0)
        self._set_status("状态：待命")
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

        discovery = discover_pdf_files(folder_path)
        file_paths = discovery.files
        self._append_discovery_messages(discovery.skipped, discovery.errors)
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

    def _append_discovery_messages(
        self,
        skipped: list[tuple[Path, str]],
        errors: list[str],
    ) -> None:
        if skipped:
            preview = "；".join(f"{path.name}（{reason}）" for path, reason in skipped[:3])
            if len(skipped) > 3:
                preview = f"{preview}；另有 {len(skipped) - 3} 个文件"
            self._append_log(f"已跳过 {len(skipped)} 个无效或不支持的 PDF：{preview}")
        for error in errors[:3]:
            self._append_log(f"扫描目录时遇到问题：{error}")

    def _build_local_delete_detail_text(self, duplicate_records: list[InvoiceRecord]) -> str:
        if not duplicate_records:
            return "当前没有可移动的本地重复文件。"

        lines: list[str] = []
        for index, record in enumerate(duplicate_records, start=1):
            lines.append(f"{index}. {record.file_name}")
            lines.append(f"   路径：{record.file_path}")
            if record.file_hash:
                lines.append(f"   文件指纹：{record.file_hash[:12]}…")
            summary_parts = [
                f"发票号码：{record.invoice_number or '未识别'}",
                f"金额：{record.total_amount if record.total_amount is not None else '未识别'}",
                f"日期：{record.invoice_date or '未识别'}",
            ]
            lines.append(f"   {'；'.join(summary_parts)}")
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
                record.parse_success,
                record.duplicate_file,
                record.duplicate_invoice,
                record.duplicate_invoice_conflict,
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

    def _resolve_export_output_path(self, output_path: Path) -> Path | None:
        if not output_path.exists():
            return output_path

        new_path = self._build_unique_export_path(output_path)
        self.output_path = new_path
        self.output_path_label.setText(f"输出路径：{self.output_path}")
        self._append_log(f"目标 Excel 已存在，为避免覆盖已自动另存为：{new_path}")
        return new_path

    def _configured_template_path(self) -> Path | None:
        configured_path = str(self.config.get("excel_template_path", "")).strip()
        if not configured_path:
            return None
        template_path = Path(configured_path)
        if template_path.exists():
            return template_path
        self._append_log(f"配置的 Excel 模板不存在，已使用默认导出格式：{template_path}")
        return None

    def _confirm_open_exported_file(self, exported_path: Path) -> None:
        reply = QMessageBox.question(
            self,
            "Excel 导出完成",
            (
                f"Excel 文件已生成：\n{exported_path}\n\n"
                "是否立即打开这个 Excel 文件？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(exported_path)))
        if opened:
            self._append_log(f"已请求系统打开 Excel 文件：{exported_path}")
            return

        self._warn(
            "打开失败",
            f"系统未能打开这个 Excel 文件，请手动打开：\n{exported_path}",
        )
        self._append_log(f"打开 Excel 文件失败：{exported_path}")

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
        except Exception:
            logger.warning("Failed to move file to trash: %s", safe_log_path(path))
            return False, "移动到废纸篓/回收站失败"

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
        self.cancel_button.setEnabled(running)
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
        self.file_button.setEnabled(not running)
        self.folder_button.setEnabled(not running)
        self.output_button.setEnabled(not running)

    def _show_log_page(self) -> None:
        self._sync_log_page_summary()
        self.page_stack.setCurrentWidget(self.log_page)

    def _show_main_page(self) -> None:
        self.page_stack.setCurrentWidget(self.main_page)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        if hasattr(self, "log_status_summary_label"):
            self.log_status_summary_label.setText(text)

    def _sync_log_page_summary(self) -> None:
        if hasattr(self, "log_file_summary_label"):
            self.log_file_summary_label.setText(f"当前文件：{len(self.selected_files)}")
        if hasattr(self, "log_status_summary_label"):
            self.log_status_summary_label.setText(self.status_label.text())

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] {message}")
        if hasattr(self, "log_count_label"):
            self.log_count_label.setText(
                f"日志条数：{self.log_box.document().blockCount()}"
            )

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _initial_output_path(self) -> Path:
        saved_dir = self.config.get("default_output_dir", "")
        base_dir = Path(saved_dir) if saved_dir else desktop_dir()
        filename = f"发票汇总_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return base_dir / filename

    def _configure_toolbar_button(
        self,
        button: QPushButton,
        *,
        minimum_width: int,
    ) -> None:
        button.setMinimumWidth(minimum_width)
        button.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #111827;
                font-size: 14px;
            }
            QMainWindow {
                background: #eef3f7;
            }
            QFrame#TopPanel, QFrame#QueuePanel, QFrame#ResultsPanel,
            QFrame#LogHeaderPanel, QFrame#LogContentPanel {
                background: #ffffff;
                border: 1px solid #d7e1ea;
                border-radius: 12px;
            }
            QFrame#TopPanel {
                background: #f5f9fc;
            }
            QFrame#TopActionCard, QFrame#TopStatusCard {
                background: #ffffff;
                border: 1px solid #dbe6ef;
                border-radius: 10px;
            }
            QFrame#ResultsControlsPanel {
                background: #f5f9fc;
                border: 1px solid #d8e5ee;
                border-radius: 10px;
            }
            QFrame#ControlGroup {
                background: #ffffff;
                border: 1px solid #dbe6ef;
                border-radius: 9px;
            }
            QLabel#SectionTitle {
                font-size: 16px;
                font-weight: 700;
                color: #1e293b;
            }
            QLabel#ControlGroupTitle {
                font-size: 11px;
                font-weight: 700;
                color: #64748b;
                letter-spacing: 0.5px;
            }
            QLabel#AmountSummary {
                font-size: 14px;
                font-weight: 600;
                color: #3d6f8e;
            }
            QLabel#SummaryBadge {
                font-size: 14px;
                font-weight: 700;
                color: #245e7a;
                background: #edf8fd;
                border: 1px solid #cce7f3;
                border-radius: 8px;
                padding: 6px 10px;
            }
            QLabel#TopStatusLabel,
            QLabel#InlineLabel {
                color: #334155;
                font-weight: 600;
            }
            QLabel#TopMetricLabel {
                color: #1e293b;
                font-size: 13px;
                font-weight: 700;
                background: #edf8fd;
                border: 1px solid #cce7f3;
                border-radius: 8px;
                padding: 5px 9px;
            }
            QLabel#PathLabel {
                color: #1f2937;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#HintLabel {
                color: #475569;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#FilterStatusLabel {
                color: #475569;
                font-weight: 700;
                padding-left: 4px;
            }
            QPushButton {
                color: #1e293b;
                min-height: 32px;
                padding: 0 14px;
                border-radius: 8px;
                border: 1px solid #b7c6d4;
                background: #f8fafc;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #edf5fb;
                border-color: #7fa0b6;
            }
            QPushButton:pressed {
                background: #dfeef7;
            }
            QPushButton#PrimaryActionButton {
                font-weight: 700;
                color: #15384a;
                background: #dff0f8;
                border: 2px solid #5d8398;
            }
            QPushButton#PrimaryActionButton:hover {
                background: #d1e9f5;
                border-color: #486f85;
            }
            QPushButton#HeaderActionButton {
                font-weight: 600;
                color: #203748;
                background: #f8fafc;
                border: 2px solid #7790a2;
            }
            QPushButton#HeaderActionButton:hover {
                background: #edf5fb;
                border-color: #5e7a8f;
            }
            QPushButton#FilterButton {
                color: #334155;
                min-height: 28px;
                padding: 0 12px;
                font-weight: 600;
                background: #ffffff;
                border: 1px solid #b9c8d6;
            }
            QPushButton#FilterButton:checked {
                color: #10384c;
                background: #d9eef8;
                border: 2px solid #2f6f89;
            }
            QPushButton#DangerActionButton {
                font-weight: 600;
                color: #8a2428;
                background: #fff1f0;
                border: 2px solid #d08f8b;
            }
            QPushButton#DangerActionButton:hover {
                background: #ffe4e1;
                border-color: #bd6f6a;
            }
            QPushButton:disabled {
                color: #64748b;
                background: #eef2f6;
                border-color: #cbd5df;
            }
            QPushButton#PrimaryActionButton:disabled,
            QPushButton#HeaderActionButton:disabled,
            QPushButton#DangerActionButton:disabled,
            QPushButton#FilterButton:disabled {
                color: #64748b;
                background: #eef2f6;
                border-color: #cbd5df;
            }
            QTableWidget {
                color: #111827;
                font-size: 12px;
                gridline-color: #dfe6ed;
                background: #ffffff;
                alternate-background-color: #f7fafc;
                selection-background-color: #cfe8f3;
                selection-color: #0f172a;
                border: 1px solid #ccd7e2;
                border-radius: 6px;
            }
            QTableWidget::item {
                padding: 3px 6px;
            }
            QHeaderView::section {
                color: #334155;
                font-size: 12px;
                background: #e7eef5;
                padding: 5px 6px;
                border: 0;
                border-right: 1px solid #dce3ea;
                border-bottom: 1px solid #dce3ea;
                font-weight: 700;
            }
            QTextEdit {
                color: #1f2937;
                background: #fbfdff;
                border: 1px solid #d7e1ea;
                border-radius: 8px;
                padding: 6px;
                selection-background-color: #cfe8f3;
                selection-color: #0f172a;
            }
            QListWidget {
                color: #1f2937;
                font-size: 12px;
                background: #fbfdff;
                border: 1px solid #d7e1ea;
                border-radius: 8px;
                padding: 3px;
                selection-background-color: #d9eef8;
                selection-color: #0f172a;
            }
            QListWidget::item {
                color: #1f2937;
                min-height: 18px;
                padding: 1px 6px;
            }
            QListWidget::item:alternate {
                background: #f7fafc;
            }
            QProgressBar {
                color: #0f172a;
                min-height: 22px;
                border: 1px solid #c7d2da;
                border-radius: 8px;
                background: #e8eef4;
                text-align: center;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background: #9ed4e7;
                border-radius: 7px;
            }
            """
        )
