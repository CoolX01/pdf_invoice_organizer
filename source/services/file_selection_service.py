from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from utils.file_utils import is_pdf_file, validate_pdf_file


@dataclass
class FileDiscoveryResult:
    files: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def discover_pdf_files(folder: Path, recursive: bool = True) -> FileDiscoveryResult:
    result = FileDiscoveryResult()
    iterator = folder.rglob("*") if recursive else folder.iterdir()

    try:
        for path in iterator:
            try:
                if not is_pdf_file(path):
                    continue
                valid, reason = validate_pdf_file(path)
            except OSError:
                result.skipped.append((path, "读取失败"))
                continue

            if valid:
                result.files.append(path)
            else:
                result.skipped.append((path, reason))
    except OSError:
        result.errors.append("无法扫描目录")

    result.files.sort(key=lambda item: item.name.lower())
    return result
