from __future__ import annotations

import os
from pathlib import Path
import sys


APP_NAME = "PDF发票自动整理归纳工具"


def resource_dir() -> Path:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            meipass_path = Path(meipass).resolve()
            candidates.extend(
                [
                    meipass_path,
                    meipass_path / "Resources",
                    meipass_path.parent / "Resources",
                ]
            )

        executable_path = Path(sys.executable).resolve()
        candidates.extend(
            [
                executable_path.parent,
                executable_path.parent.parent / "Resources",
            ]
        )
    else:
        candidates.append(Path(__file__).resolve().parents[1])

    for candidate in candidates:
        if (candidate / "config" / "default_settings.json").exists():
            return candidate

    return candidates[0] if candidates else Path.cwd()


def user_config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def user_log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME / "logs"
        return Path.home() / "AppData" / "Local" / APP_NAME / "logs"

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / APP_NAME / "logs"
    return Path.home() / ".local" / "state" / APP_NAME / "logs"

