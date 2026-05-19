from __future__ import annotations

import os
from pathlib import Path
import site


QT_API = ""

try:
    from PyQt6.QtCore import QFile, QThread, Qt, QUrl, pyqtSignal as Signal
    from PyQt6.QtGui import (
        QAction,
        QColor,
        QDesktopServices,
        QDragEnterEvent,
        QDropEvent,
    )
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QFileDialog,
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
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt6"
except ImportError:
    def _bootstrap_pyside_runtime() -> None:
        candidate_roots: list[Path] = []
        for root in site.getsitepackages():
            candidate_roots.append(Path(root))

        user_site = site.getusersitepackages()
        if user_site:
            candidate_roots.append(Path(user_site))

        for root in candidate_roots:
            qt_root = root / "PySide6" / "Qt"
            plugins = qt_root / "plugins"
            libraries = qt_root / "lib"
            if not plugins.exists():
                continue
            os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))
            os.environ.setdefault(
                "QT_QPA_PLATFORM_PLUGIN_PATH",
                str(plugins / "platforms"),
            )
            if libraries.exists():
                os.environ.setdefault("DYLD_FRAMEWORK_PATH", str(libraries))
                os.environ.setdefault("DYLD_LIBRARY_PATH", str(libraries))
            break

    _bootstrap_pyside_runtime()

    from PySide6.QtCore import QFile, QThread, Qt, QUrl, Signal
    from PySide6.QtGui import (
        QAction,
        QColor,
        QDesktopServices,
        QDragEnterEvent,
        QDropEvent,
    )
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QFileDialog,
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
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PySide6"
