from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from machue.config import HueConfig, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_load_missing_returns_empty_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            cfg = load_config(path)
            self.assertIsNone(cfg.bridge_ip)
            self.assertIsNone(cfg.username)

    def test_save_then_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(HueConfig(bridge_ip="192.168.1.2", username="abc123"), path)
            loaded = load_config(path)
            self.assertEqual(loaded.bridge_ip, "192.168.1.2")
            self.assertEqual(loaded.username, "abc123")


if __name__ == "__main__":
    unittest.main()
