from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_hash(path: Path, chunk_size: int = 8192) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def is_pdf_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".pdf"


def validate_pdf_file(path: Path) -> tuple[bool, str]:
    if path.suffix.lower() != ".pdf":
        return False, "不是 PDF 文件"
    if not path.exists():
        return False, "文件不存在"
    if not path.is_file():
        return False, "不是普通文件"

    try:
        size = path.stat().st_size
    except OSError:
        return False, "无法读取文件信息"
    if size <= 0:
        return False, "文件为空"

    try:
        with path.open("rb") as file:
            header = file.read(5)
    except OSError:
        return False, "无法读取文件"

    if header != b"%PDF-":
        return False, "文件头不是有效 PDF"
    return True, ""


def is_supported_pdf_file(path: Path) -> bool:
    valid, _ = validate_pdf_file(path)
    return valid


def desktop_dir() -> Path:
    home = Path.home()
    candidate = home / "Desktop"
    return candidate if candidate.exists() else home
