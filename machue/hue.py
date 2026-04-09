from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class HueError(Exception):
    pass


@dataclass
class BridgeInfo:
    id: str
    internalipaddress: str


class HueClient:
    def __init__(self, bridge_ip: str, username: str | None = None, timeout: float = 3.0):
        self.bridge_ip = bridge_ip
        self.username = username
        self.timeout = timeout

    @staticmethod
    def discover_bridges(timeout: float = 3.0) -> list[BridgeInfo]:
        req = request.Request("https://discovery.meethue.com/", method="GET")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise HueError(f"Could not reach Hue discovery service: {exc}") from exc

        bridges: list[BridgeInfo] = []
        for item in data:
            bridge_id = item.get("id")
            ip = item.get("internalipaddress")
            if bridge_id and ip:
                bridges.append(BridgeInfo(id=bridge_id, internalipaddress=ip))
        return bridges

    def create_user(self, devicetype: str = "machue#cli") -> str:
        payload = {"devicetype": devicetype}
        data = self._request("POST", "/api", payload, include_username=False)
        self._raise_if_hue_error(data)
        username = data[0]["success"]["username"]
        self.username = username
        return username

    def get_lights(self) -> dict[str, dict[str, Any]]:
        data = self._request("GET", "/lights")
        if not isinstance(data, dict):
            raise HueError("Unexpected response format from /lights")
        return data

    def get_groups(self) -> dict[str, dict[str, Any]]:
        data = self._request("GET", "/groups")
        if not isinstance(data, dict):
            raise HueError("Unexpected response format from /groups")
        return data

    def get_scenes(self) -> dict[str, dict[str, Any]]:
        data = self._request("GET", "/scenes")
        if not isinstance(data, dict):
            raise HueError("Unexpected response format from /scenes")
        return data

    def set_light_state(self, light_id: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._request("PUT", f"/lights/{light_id}/state", state)
        self._raise_if_hue_error(data)
        return data

    def set_group_action(self, group_id: int, state: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._request("PUT", f"/groups/{group_id}/action", state)
        self._raise_if_hue_error(data)
        return data

    def recall_scene(self, scene_id: str, group_id: int) -> list[dict[str, Any]]:
        data = self._request("PUT", f"/groups/{group_id}/action", {"scene": scene_id})
        self._raise_if_hue_error(data)
        return data

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        include_username: bool = True,
    ) -> Any:
        base = f"http://{self.bridge_ip}/api"
        if include_username:
            if not self.username:
                raise HueError("Missing Hue username/token")
            url = f"{base}/{self.username}{path}"
        else:
            url = base

        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, method=method, data=body, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise HueError(f"Network error when calling Hue bridge at {url}: {exc}") from exc

    @staticmethod
    def _raise_if_hue_error(data: Any) -> None:
        if not isinstance(data, list):
            return
        for row in data:
            if not isinstance(row, dict):
                continue
            error_obj = row.get("error")
            if isinstance(error_obj, dict):
                desc = error_obj.get("description", "Unknown Hue API error")
                raise HueError(str(desc))
