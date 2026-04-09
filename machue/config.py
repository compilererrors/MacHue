from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "machue" / "config.json"


@dataclass
class HueConfig:
    bridge_ip: str | None = None
    username: str | None = None
    strict_tls: bool | None = None


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> HueConfig:
    if not path.exists():
        return HueConfig()

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return HueConfig(
        bridge_ip=data.get("bridge_ip"),
        username=data.get("username"),
        strict_tls=data.get("strict_tls"),
    )


def save_config(config: HueConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "bridge_ip": config.bridge_ip,
                "username": config.username,
                "strict_tls": config.strict_tls,
            },
            f,
            indent=2,
        )
