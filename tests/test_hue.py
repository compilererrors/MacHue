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
            "_request_v1",
            return_value=[{"success": {"username": "generated-user"}}],
        ):
            username = client.create_user()
        self.assertEqual(username, "generated-user")
        self.assertEqual(client.username, "generated-user")

    def test_request_v2_requires_username(self) -> None:
        client = HueClient("192.168.1.20", username=None)
        with self.assertRaises(HueError):
            client._request_v2("GET", "/resource/light")

    def test_request_v2_uses_https_clip_path_and_app_key(self) -> None:
        client = HueClient("192.168.1.20", username="u1")
        captured: dict[str, object] = {}

        def _fake_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            return _FakeHTTPResponse({"errors": [], "data": []})

        with patch("machue.hue.request.urlopen", side_effect=_fake_urlopen):
            result = client._request_v2("GET", "/resource/light")

        self.assertEqual(result, {"errors": [], "data": []})
        self.assertEqual(captured["url"], "https://192.168.1.20/clip/v2/resource/light")
        headers = {str(k).lower(): str(v) for k, v in dict(captured["headers"]).items()}
        self.assertEqual(headers.get("hue-application-key"), "u1")

    def test_get_lights_maps_v2_resources_to_display_ids(self) -> None:
        client = HueClient("192.168.1.20", username="u1")
        with patch.object(
            client,
            "_request_v2",
            return_value={
                "errors": [],
                "data": [
                    {"id": "rid-b", "metadata": {"name": "Beta"}, "on": {"on": True}, "dimming": {"brightness": 50}},
                    {"id": "rid-a", "metadata": {"name": "Alpha"}, "on": {"on": False}},
                ],
            },
        ):
            lights = client.get_lights()

        self.assertEqual(list(lights.keys()), ["1", "2"])
        self.assertEqual(lights["1"]["name"], "Alpha")
        self.assertEqual(lights["2"]["state"]["bri"], 127)

    def test_get_groups_and_scenes_map_scene_group_to_display_index(self) -> None:
        client = HueClient("192.168.1.20", username="u1")

        def _fake_request_v2(method: str, path: str, payload=None):
            self.assertEqual(method, "GET")
            if path == "/resource/room":
                return {
                    "errors": [],
                    "data": [
                        {
                            "id": "room-1",
                            "metadata": {"name": "Living Room"},
                            "services": [{"rtype": "grouped_light", "rid": "gl-room-1"}],
                        }
                    ],
                }
            if path == "/resource/zone":
                return {"errors": [], "data": []}
            if path == "/resource/bridge_home":
                return {
                    "errors": [],
                    "data": [{"services": [{"rtype": "grouped_light", "rid": "gl-home"}]}],
                }
            if path == "/resource/scene":
                return {
                    "errors": [],
                    "data": [
                        {
                            "id": "scene-1",
                            "metadata": {"name": "Relax"},
                            "group": {"rid": "room-1", "rtype": "room"},
                        }
                    ],
                }
            raise AssertionError(f"Unexpected path {path}")

        with patch.object(client, "_request_v2", side_effect=_fake_request_v2):
            groups = client.get_groups()
            scenes = client.get_scenes()

        self.assertIn("0", groups)
        self.assertEqual(groups["1"]["name"], "Living Room")
        self.assertEqual(scenes["scene-1"]["group"], 1)

    def test_raise_if_v2_error_raises(self) -> None:
        with self.assertRaises(HueError):
            HueClient._raise_if_v2_error({"errors": [{"description": "failure"}], "data": []})


if __name__ == "__main__":
    unittest.main()
