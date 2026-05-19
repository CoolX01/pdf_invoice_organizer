import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE_DIR))

from utils.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_default_and_example_config_use_multi_page_ocr_limit(self) -> None:
        project_dir = Path(__file__).resolve().parents[1]
        default_config = json.loads(
            (project_dir / "source" / "config" / "default_settings.json").read_text(
                encoding="utf-8"
            )
        )
        example_config = json.loads(
            (project_dir / "source" / "config" / "user_settings.example.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(default_config["max_ocr_pages"], 10)
        self.assertEqual(example_config["max_ocr_pages"], 10)
        self.assertTrue(default_config["confirm_ocr_before_analysis"])
        self.assertTrue(example_config["confirm_ocr_before_analysis"])

    def test_invalid_user_config_is_ignored_and_save_is_atomic_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "app"
            config_dir = base_dir / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "default_settings.json").write_text(
                json.dumps({"default_output_dir": "", "ocr_enabled": True}),
                encoding="utf-8",
            )

            user_dir = Path(tmp_dir) / "user-config"
            user_dir.mkdir()
            (user_dir / "user_settings.json").write_text("{broken", encoding="utf-8")

            with patch("utils.config.user_config_dir", return_value=user_dir):
                config = AppConfig(base_dir)
                self.assertTrue(config.get("ocr_enabled"))
                config.set("ocr_enabled", False)
                config.save()

            saved = json.loads((user_dir / "user_settings.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["ocr_enabled"])

            if os.name != "nt":
                self.assertEqual((user_dir.stat().st_mode & 0o777), 0o700)
                self.assertEqual(((user_dir / "user_settings.json").stat().st_mode & 0o777), 0o600)


if __name__ == "__main__":
    unittest.main()
