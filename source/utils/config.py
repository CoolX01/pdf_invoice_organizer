from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from utils.app_paths import user_config_dir

logger = logging.getLogger(__name__)


class AppConfig:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.default_config_dir = base_dir / "config"
        self.config_dir = user_config_dir()
        self.default_path = self.default_config_dir / "default_settings.json"
        self.user_path = self.config_dir / "user_settings.json"
        self.legacy_user_path = self.default_config_dir / "user_settings.json"
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        data.update(self._read_json_file(self.default_path, required=True))
        if self.user_path.exists():
            data.update(self._read_json_file(self.user_path))
        elif self.legacy_user_path.exists():
            data.update(self._read_json_file(self.legacy_user_path))
        return data

    def _read_json_file(self, path: Path, required: bool = False) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if required:
                raise
            logger.warning("Ignored invalid config file: %s", path.name)
            return {}
        if not isinstance(loaded, dict):
            if required:
                raise ValueError(f"配置文件格式错误：{path}")
            logger.warning("Ignored non-object config file: %s", path.name)
            return {}
        return loaded

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        _chmod_private(self.config_dir, directory=True)

        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.config_dir,
                prefix=f".{self.user_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_name = temp_file.name
                temp_file.write(payload)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            temp_path = Path(temp_name)
            _chmod_private(temp_path, directory=False)
            temp_path.replace(self.user_path)
            _chmod_private(self.user_path, directory=False)
        finally:
            if temp_name:
                temp_path = Path(temp_name)
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        logger.warning("Failed to remove temporary config file: %s", temp_path.name)


def _chmod_private(path: Path, directory: bool) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o700 if directory else 0o600)
    except OSError:
        logger.debug("Failed to adjust permissions for %s", path, exc_info=True)
