import sys

from qt_compat import QApplication
from ui.main_window import MainWindow
from utils.app_paths import resource_dir, user_log_dir
from utils.logging_utils import configure_logging


def run() -> None:
    base_dir = resource_dir()
    configure_logging(user_log_dir())

    app = QApplication(sys.argv)
    app.setApplicationName("PDF发票自动整理归纳工具")
    app.setOrganizationName("CodeX")
    window = MainWindow(base_dir=base_dir)
    window.show()
    sys.exit(app.exec())
