from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib import error

from machue.hue import HueClient, HueError


class _FakeHTTPResponse:
    def __init__(self, payload: object):
        self._payload = payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class HueTests(unittest.TestCase):
    def test_discover_bridges_parses_valid_items(self) -> None:
        payload = [
            {"id": "a", "internalipaddress": "192.168.1.10"},
            {"id": "b"},  # invalid, filtered
        ]
        with patch("machue.hue.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            bridges = HueClient.discover_bridges()
        self.assertEqual(len(bridges), 1)
        self.assertEqual(bridges[0].id, "a")
        self.assertEqual(bridges[0].internalipaddress, "192.168.1.10")

    def test_discover_bridges_network_error_raises_hue_error(self) -> None:
        with patch("machue.hue.request.urlopen", side_effect=error.URLError("boom")):
            with self.assertRaises(HueError):
                HueClient.discover_bridges()

    def test_create_user_updates_username(self) -> None:
        client = HueClient("192.168.1.20")
        with patch.object(
            client,
            "_request",
            return_value=[{"success": {"username": "generated-user"}}],
        ):
            username = client.create_user()
        self.assertEqual(username, "generated-user")
        self.assertEqual(client.username, "generated-user")

    def test_request_requires_username_for_authenticated_paths(self) -> None:
        client = HueClient("192.168.1.20", username=None)
        with self.assertRaises(HueError):
            client._request("GET", "/lights")

    def test_request_uses_https_for_bridge_calls(self) -> None:
        client = HueClient("192.168.1.20", username="u1")
        captured: dict[str, str] = {}

        def _fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            return _FakeHTTPResponse({})

        with patch("machue.hue.request.urlopen", side_effect=_fake_urlopen):
            result = client._request("GET", "/lights")

        self.assertEqual(result, {})
        self.assertEqual(captured["url"], "https://192.168.1.20/api/u1/lights")

    def test_raise_if_hue_error_raises(self) -> None:
        with self.assertRaises(HueError):
            HueClient._raise_if_hue_error(
                [{"error": {"type": 1, "address": "/", "description": "failure"}}]
            )


if __name__ == "__main__":
    unittest.main()
