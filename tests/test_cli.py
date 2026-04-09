from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from machue import cli


def _run_cli(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with patch("sys.argv", argv):
        with redirect_stdout(buf):
            code = cli.main()
    return code, buf.getvalue()


class CLITests(unittest.TestCase):
    def test_config_set_then_show(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            code, out = _run_cli(
                [
                    "machue",
                    "--config",
                    str(cfg),
                    "config",
                    "set",
                    "--bridge-ip",
                    "192.168.1.10",
                    "--username",
                    "token-1",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("Updated config", out)

            code, out = _run_cli(["machue", "--config", str(cfg), "config", "show"])
            self.assertEqual(code, 0)
            self.assertIn("bridge_ip: 192.168.1.10", out)
            self.assertIn("username: token-1", out)

    def test_login_writes_token_without_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            code, out = _run_cli(
                [
                    "machue",
                    "--config",
                    str(cfg),
                    "login",
                    "--username",
                    "token-login",
                    "--bridge-ip",
                    "192.168.1.11",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("Saved credentials", out)

            code, out = _run_cli(["machue", "--config", str(cfg), "config", "show"])
            self.assertEqual(code, 0)
            self.assertIn("bridge_ip: 192.168.1.11", out)
            self.assertIn("username: token-login", out)

    def test_missing_auth_for_list_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "empty.json"
            code, out = _run_cli(["machue", "--config", str(cfg), "list"])
            self.assertEqual(code, 1)
            self.assertIn("Missing bridge IP", out)

    def test_scene_uses_scene_group_if_not_overridden(self) -> None:
        fake_client = object.__new__(cli.HueClient)
        fake_client.get_scenes = lambda: {"abc": {"group": "3"}}  # type: ignore[attr-defined]
        group = cli._resolve_scene_group(fake_client, "abc", None)  # type: ignore[arg-type]
        self.assertEqual(group, 3)


if __name__ == "__main__":
    unittest.main()
