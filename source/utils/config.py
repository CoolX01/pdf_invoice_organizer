from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.app_paths import user_config_dir


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
        if self.default_path.exists():
            data.update(json.loads(self.default_path.read_text(encoding="utf-8")))
        if self.user_path.exists():
            data.update(json.loads(self.user_path.read_text(encoding="utf-8")))
        elif self.legacy_user_path.exists():
            data.update(json.loads(self.legacy_user_path.read_text(encoding="utf-8")))
        return data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.user_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
