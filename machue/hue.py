from __future__ import annotations

import json
import ssl
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
    def __init__(
        self,
        bridge_ip: str,
        username: str | None = None,
        timeout: float = 3.0,
        insecure_tls: bool = True,
    ):
        self.bridge_ip = bridge_ip
        self.username = username
        self.timeout = timeout
        self.insecure_tls = insecure_tls
        self._light_id_map: dict[str, str] = {}
        self._grouped_light_map: dict[int, str] = {}
        self._group_display_by_rid: dict[str, int] = {}
        self._all_grouped_light_id: str | None = None

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
        data = self._request_v1("POST", "", payload, include_username=False)
        self._raise_if_hue_error(data)
        username = data[0]["success"]["username"]
        self.username = username
        return username

    def get_lights(self) -> dict[str, dict[str, Any]]:
        data = self._extract_v2_data(self._request_v2("GET", "/resource/light"))
        self._light_id_map = {}

        rows: dict[str, dict[str, Any]] = {}
        sorted_lights = sorted(
            data,
            key=lambda item: (
                str(item.get("metadata", {}).get("name", "")).lower(),
                str(item.get("id", "")),
            ),
        )
        for idx, light in enumerate(sorted_lights, start=1):
            rid = light.get("id")
            if not isinstance(rid, str):
                continue
            name = str(light.get("metadata", {}).get("name", f"Light {idx}"))
            on_value = bool(light.get("on", {}).get("on", False))
            bri_value = self._bri_100_to_254(light.get("dimming", {}).get("brightness"))

            state: dict[str, Any] = {"on": on_value}
            if bri_value is not None:
                state["bri"] = bri_value

            display_id = str(idx)
            self._light_id_map[display_id] = rid
            rows[display_id] = {"name": name, "state": state, "id_v2": rid}
        return rows

    def get_groups(self) -> dict[str, dict[str, Any]]:
        rooms = self._extract_v2_data(self._request_v2("GET", "/resource/room"))
        zones = self._extract_v2_data(self._request_v2("GET", "/resource/zone"))
        bridge_homes = self._extract_v2_data(self._request_v2("GET", "/resource/bridge_home"))

        self._grouped_light_map = {}
        self._group_display_by_rid = {}
        self._all_grouped_light_id = None

        for home in bridge_homes:
            grouped_rid = self._find_grouped_light_rid(home)
            if grouped_rid:
                self._all_grouped_light_id = grouped_rid
                break

        rows: dict[str, dict[str, Any]] = {"0": {"name": "All lights", "type": "BridgeHome"}}
        if self._all_grouped_light_id:
            self._grouped_light_map[0] = self._all_grouped_light_id

        containers: list[tuple[str, dict[str, Any]]] = []
        containers.extend(("Room", room) for room in rooms)
        containers.extend(("Zone", zone) for zone in zones)
        containers.sort(
            key=lambda item: (
                str(item[1].get("metadata", {}).get("name", "")).lower(),
                str(item[1].get("id", "")),
            )
        )

        for idx, (gtype, group) in enumerate(containers, start=1):
            gid = str(idx)
            name = str(group.get("metadata", {}).get("name", f"{gtype} {idx}"))
            rows[gid] = {"name": name, "type": gtype}

            group_rid = group.get("id")
            if isinstance(group_rid, str):
                self._group_display_by_rid[group_rid] = idx

            grouped_rid = self._find_grouped_light_rid(group)
            if grouped_rid:
                self._grouped_light_map[idx] = grouped_rid
        return rows

    def get_scenes(self) -> dict[str, dict[str, Any]]:
        if not self._group_display_by_rid:
            self.get_groups()

        data = self._extract_v2_data(self._request_v2("GET", "/resource/scene"))
        scenes: dict[str, dict[str, Any]] = {}
        sorted_scenes = sorted(
            data,
            key=lambda item: (
                str(item.get("metadata", {}).get("name", "")).lower(),
                str(item.get("id", "")),
            ),
        )
        for scene in sorted_scenes:
            scene_id = scene.get("id")
            if not isinstance(scene_id, str):
                continue

            name = str(scene.get("metadata", {}).get("name", scene_id))
            group_rid = scene.get("group", {}).get("rid")
            if isinstance(group_rid, str) and group_rid in self._group_display_by_rid:
                group_value: Any = self._group_display_by_rid[group_rid]
            elif isinstance(group_rid, str):
                group_value = group_rid
            else:
                group_value = "-"

            scenes[scene_id] = {"name": name, "type": "scene", "group": group_value}
        return scenes

    def set_light_state(self, light_id: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        rid = self._resolve_light_rid(light_id)
        payload = self._build_light_payload(state)
        if not payload:
            return []
        return self._extract_v2_data(self._request_v2("PUT", f"/resource/light/{rid}", payload))

    def set_group_action(self, group_id: int, state: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._build_light_payload(state)
        if not payload:
            return []

        if not self._grouped_light_map:
            self.get_groups()

        if group_id == 0:
            if self._all_grouped_light_id:
                return self._extract_v2_data(
                    self._request_v2(
                        "PUT",
                        f"/resource/grouped_light/{self._all_grouped_light_id}",
                        payload,
                    )
                )
            for lid in list(self.get_lights().keys()):
                self.set_light_state(lid, state)
            return []

        grouped_rid = self._grouped_light_map.get(group_id)
        if not grouped_rid:
            raise HueError(f"Group id {group_id} not found")
        return self._extract_v2_data(
            self._request_v2("PUT", f"/resource/grouped_light/{grouped_rid}", payload)
        )

    def recall_scene(self, scene_id: str, group_id: int) -> list[dict[str, Any]]:
        del group_id  # The scene itself is already bound to its group in API v2.
        payload = {"recall": {"action": "active"}}
        return self._extract_v2_data(self._request_v2("PUT", f"/resource/scene/{scene_id}", payload))

    @staticmethod
    def _bri_100_to_254(value: Any) -> int | None:
        if not isinstance(value, (int, float)):
            return None
        bri = int(round((float(value) / 100.0) * 254.0))
        return max(1, min(254, bri))

    @staticmethod
    def _bri_254_to_100(value: Any) -> float:
        bri = int(value)
        bri = max(1, min(254, bri))
        return round((bri / 254.0) * 100.0, 2)

    @staticmethod
    def _find_grouped_light_rid(resource_obj: dict[str, Any]) -> str | None:
        for svc in resource_obj.get("services", []):
            if not isinstance(svc, dict):
                continue
            if svc.get("rtype") != "grouped_light":
                continue
            rid = svc.get("rid")
            if isinstance(rid, str):
                return rid
        return None

    def _resolve_light_rid(self, light_id: str) -> str:
        if light_id in self._light_id_map:
            return self._light_id_map[light_id]
        if light_id in self._light_id_map.values():
            return light_id
        self.get_lights()
        if light_id in self._light_id_map:
            return self._light_id_map[light_id]
        if light_id in self._light_id_map.values():
            return light_id
        raise HueError(f"Light id {light_id} not found")

    def _build_light_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if "on" in state:
            payload["on"] = {"on": bool(state["on"])}
        if "bri" in state:
            payload["dimming"] = {"brightness": self._bri_254_to_100(state["bri"])}
        return payload

    def _request_v1(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        include_username: bool = True,
    ) -> Any:
        base = f"https://{self.bridge_ip}/api"
        if include_username:
            if not self.username:
                raise HueError("Missing Hue username/token")
            url = f"{base}/{self.username}{path}"
        else:
            url = f"{base}{path}"

        headers: dict[str, str] = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return self._urlopen_json(method, url, payload, headers)

    def _request_v2(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.username:
            raise HueError("Missing Hue username/token")
        url = f"https://{self.bridge_ip}/clip/v2{path}"
        headers: dict[str, str] = {"hue-application-key": self.username}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return self._urlopen_json(method, url, payload, headers)

    def _urlopen_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> Any:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = request.Request(url, method=method, data=body, headers=headers)
        urlopen_kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self.insecure_tls and url.startswith("https://"):
            # Hue bridges can present certificates not trusted by local OS stores.
            urlopen_kwargs["context"] = ssl._create_unverified_context()
        try:
            with request.urlopen(req, **urlopen_kwargs) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise HueError(
                    "TLS certificate verification failed for Hue bridge. "
                    "Use --insecure-tls (or save with `machue config set --insecure-tls`) "
                    "if the bridge certificate is not trusted by your system."
                ) from exc
            if isinstance(reason, str) and "CERTIFICATE_VERIFY_FAILED" in reason:
                raise HueError(
                    "TLS certificate verification failed for Hue bridge. "
                    "Use --insecure-tls (or save with `machue config set --insecure-tls`) "
                    "if the bridge certificate is not trusted by your system."
                ) from exc
            raise HueError(f"Network error when calling Hue bridge at {url}: {exc}") from exc

    def _extract_v2_data(self, payload: Any) -> list[dict[str, Any]]:
        self._raise_if_v2_error(payload)
        data = payload.get("data")
        if not isinstance(data, list):
            raise HueError("Unexpected response format from Hue API v2")
        return [row for row in data if isinstance(row, dict)]

    @staticmethod
    def _raise_if_v2_error(payload: Any) -> None:
        if not isinstance(payload, dict):
            raise HueError("Unexpected response format from Hue API v2")
        errors = payload.get("errors", [])
        if not isinstance(errors, list):
            raise HueError("Unexpected response format from Hue API v2 errors")
        for row in errors:
            if not isinstance(row, dict):
                continue
            desc = row.get("description", "Unknown Hue API v2 error")
            raise HueError(str(desc))

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
