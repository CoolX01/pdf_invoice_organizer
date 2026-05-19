from __future__ import annotations

import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    _chmod_private(log_dir, directory=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_500_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    _chmod_private(log_file, directory=False)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)


def safe_log_path(path: Path | str) -> str:
    path_text = str(path)
    suffix = Path(path_text).suffix.lower()
    digest = hashlib.sha256(path_text.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"<file:{digest}{suffix}>"


def _chmod_private(path: Path, directory: bool) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o700 if directory else 0o600)
    except OSError:
        logging.getLogger(__name__).debug(
            "Failed to adjust permissions for log path",
            exc_info=True,
        )
