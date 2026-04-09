from __future__ import annotations

import argparse
from pathlib import Path

from machue.config import DEFAULT_CONFIG_PATH, HueConfig, load_config, save_config
from machue.hue import HueClient, HueError


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MacHue CLI - Philips Hue via terminal")
    p.add_argument("--bridge-ip", help="Hue bridge IP")
    p.add_argument("--username", help="Hue API username/token")
    p.add_argument(
        "--config",
        type=lambda value: Path(value).expanduser(),
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})",
    )
    tls_group = p.add_mutually_exclusive_group()
    tls_group.add_argument(
        "--strict-tls",
        dest="strict_tls",
        action="store_true",
        help="Enable strict TLS certificate verification for bridge requests",
    )
    tls_group.add_argument(
        "--insecure-tls",
        dest="strict_tls",
        action="store_false",
        help="Disable TLS certificate verification for bridge requests",
    )
    p.set_defaults(strict_tls=None)

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("discover", help="Discover bridges via meethue discovery service")

    pair = sub.add_parser("pair", help="Pair with bridge (press link button first)")
    pair.add_argument("--devicetype", default="machue#cli", help="Hue devicetype")

    login = sub.add_parser("login", help="Save username/token to config (no pairing)")
    login.add_argument("--username", required=True, help="Hue API username/token to save")
    login.add_argument("--bridge-ip", help="Bridge IP to save with token")

    cfg = sub.add_parser("config", help="Manage local config")
    cfg_sub = cfg.add_subparsers(dest="config_cmd", required=True)

    cfg_sub.add_parser("show", help="Show current config")

    cfg_set = cfg_sub.add_parser("set", help="Set bridge IP and/or username token")
    cfg_set.add_argument("--bridge-ip", help="Bridge IP to save")
    cfg_set.add_argument("--username", help="Hue API username/token to save")
    cfg_tls = cfg_set.add_mutually_exclusive_group()
    cfg_tls.add_argument(
        "--strict-tls",
        dest="strict_tls",
        action="store_true",
        help="Save strict TLS mode",
    )
    cfg_tls.add_argument(
        "--insecure-tls",
        dest="strict_tls",
        action="store_false",
        help="Save insecure TLS mode",
    )
    cfg_set.set_defaults(strict_tls=None)

    cfg_clear = cfg_sub.add_parser("clear", help="Clear fields from config")
    cfg_clear.add_argument("--bridge-ip", action="store_true", help="Clear saved bridge IP")
    cfg_clear.add_argument("--username", action="store_true", help="Clear saved username/token")
    cfg_clear.add_argument(
        "--strict-tls",
        dest="clear_strict_tls",
        action="store_true",
        help="Clear saved strict TLS setting",
    )
    cfg_clear.add_argument(
        "--all",
        action="store_true",
        help="Clear bridge IP, username/token, and strict TLS setting",
    )

    sub.add_parser("list", help="List all lights")
    sub.add_parser("groups", help="List all groups/rooms/zones")

    scenes = sub.add_parser("scenes", help="List stored scenes")
    scenes.add_argument("--group", type=int, help="Only show scenes for group id")
    scenes.add_argument("--name", help="Filter scene name (case-insensitive)")

    scene = sub.add_parser("scene", help="Recall a scene by scene id")
    scene.add_argument("scene_id", help="Hue scene id")
    scene.add_argument("--group", type=int, help="Override group id for recall")

    on = sub.add_parser("on", help="Turn on light or all")
    on.add_argument("target", help="Light id or 'all'")

    off = sub.add_parser("off", help="Turn off light or all")
    off.add_argument("target", help="Light id or 'all'")

    toggle = sub.add_parser("toggle", help="Toggle light or all")
    toggle.add_argument("target", help="Light id or 'all'")

    bri = sub.add_parser("brightness", help="Set brightness (1-254)")
    bri.add_argument("target", help="Light id or 'all'")
    bri.add_argument("value", type=int, help="Brightness value 1..254")

    sub.add_parser("tui", help="Start interactive TUI")
    return p


def _resolve_config(args: argparse.Namespace) -> tuple[HueConfig, str | None, str | None, bool]:
    cfg = load_config(args.config)
    bridge_ip = args.bridge_ip or cfg.bridge_ip
    username = args.username or cfg.username
    if args.strict_tls is None:
        strict_tls = bool(cfg.strict_tls)
    else:
        strict_tls = bool(args.strict_tls)
    return cfg, bridge_ip, username, strict_tls


def _require_bridge_ip(bridge_ip: str | None) -> str:
    if not bridge_ip:
        raise HueError("Missing bridge IP. Set --bridge-ip or use config.")
    return bridge_ip


def _require_auth(bridge_ip: str | None, username: str | None) -> tuple[str, str]:
    ip = _require_bridge_ip(bridge_ip)
    if not username:
        raise HueError("Missing username/token. Run `pair` first.")
    return ip, username


def _print_lights(client: HueClient) -> None:
    lights = client.get_lights()
    print("ID  Name                           State  Bri")
    for lid, light in sorted(lights.items(), key=lambda kv: int(kv[0])):
        state = "on " if light.get("state", {}).get("on") else "off"
        bri = light.get("state", {}).get("bri", "-")
        name = str(light.get("name", "Unnamed"))[:30]
        print(f"{lid:>2}  {name:<30} {state:<5} {bri}")


def _print_config(config: HueConfig, path: Path) -> None:
    print(f"config_path: {path}")
    print(f"bridge_ip: {config.bridge_ip or '-'}")
    print(f"username: {config.username or '-'}")
    if config.strict_tls is None:
        tls_mode = "insecure (default)"
    else:
        tls_mode = "strict" if config.strict_tls else "insecure"
    print(f"tls_mode: {tls_mode}")


def _config_set(
    cfg: HueConfig,
    path: Path,
    bridge_ip: str | None = None,
    username: str | None = None,
    strict_tls: bool | None = None,
) -> None:
    if bridge_ip is None and username is None and strict_tls is None:
        raise HueError("Nothing to set. Use --bridge-ip, --username and/or --strict-tls/--insecure-tls.")
    if bridge_ip is not None:
        cfg.bridge_ip = bridge_ip
    if username is not None:
        cfg.username = username
    if strict_tls is not None:
        cfg.strict_tls = strict_tls
    save_config(cfg, path)


def _config_clear(
    cfg: HueConfig,
    path: Path,
    clear_bridge_ip: bool,
    clear_username: bool,
    clear_strict_tls: bool,
    clear_all: bool,
) -> None:
    if clear_all:
        cfg.bridge_ip = None
        cfg.username = None
        cfg.strict_tls = None
    else:
        if clear_bridge_ip:
            cfg.bridge_ip = None
        if clear_username:
            cfg.username = None
        if clear_strict_tls:
            cfg.strict_tls = None
    if not (clear_bridge_ip or clear_username or clear_strict_tls or clear_all):
        raise HueError("Nothing to clear. Use --bridge-ip, --username, --strict-tls or --all.")
    save_config(cfg, path)


def _set_on_off(client: HueClient, target: str, on: bool) -> None:
    if target == "all":
        client.set_group_action(0, {"on": on})
        return
    client.set_light_state(target, {"on": on})


def _print_groups(client: HueClient) -> None:
    groups = client.get_groups()
    print("ID  Name                           Type")
    for gid, group in sorted(groups.items(), key=lambda kv: int(kv[0])):
        name = str(group.get("name", "Unnamed"))[:30]
        gtype = str(group.get("type", "-"))[:12]
        print(f"{gid:>2}  {name:<30} {gtype}")


def _print_scenes(client: HueClient, group: int | None = None, name_filter: str | None = None) -> None:
    scenes = client.get_scenes()
    needle = name_filter.lower() if name_filter else None

    rows: list[tuple[str, dict]] = []
    for scene_id, scene in scenes.items():
        scene_group = scene.get("group")
        if group is not None and str(scene_group) != str(group):
            continue
        if needle:
            scene_name = str(scene.get("name", ""))
            if needle not in scene_name.lower():
                continue
        rows.append((scene_id, scene))

    rows.sort(key=lambda kv: (str(kv[1].get("name", "")).lower(), kv[0]))

    print("Scene ID         Name                           Type        Group")
    for scene_id, scene in rows:
        name = str(scene.get("name", "Unnamed"))[:30]
        stype = str(scene.get("type", "-"))[:10]
        scene_group = str(scene.get("group", "-"))
        print(f"{scene_id:<16} {name:<30} {stype:<10} {scene_group}")
    print(f"Total scenes: {len(rows)}")


def _resolve_scene_group(client: HueClient, scene_id: str, requested_group: int | None) -> int:
    if requested_group is not None:
        return requested_group

    scenes = client.get_scenes()
    scene = scenes.get(scene_id)
    if scene is None:
        raise HueError(f"Scene id {scene_id} not found")

    scene_group = scene.get("group")
    if scene_group is None:
        return 0
    try:
        return int(str(scene_group))
    except ValueError:
        # API v2 scenes may contain resource IDs instead of numeric group indexes.
        return 0


def _set_brightness(client: HueClient, target: str, value: int) -> None:
    if value < 1 or value > 254:
        raise HueError("Brightness must be between 1 and 254")
    payload = {"on": True, "bri": value}
    if target == "all":
        client.set_group_action(0, payload)
        return
    client.set_light_state(target, payload)


def _toggle(client: HueClient, target: str) -> None:
    lights = client.get_lights()
    if target == "all":
        for lid, light in lights.items():
            current = bool(light.get("state", {}).get("on", False))
            client.set_light_state(lid, {"on": not current})
        return
    if target not in lights:
        raise HueError(f"Light id {target} not found")
    current = bool(lights[target].get("state", {}).get("on", False))
    client.set_light_state(target, {"on": not current})


def main() -> int:
    args = _parser().parse_args()
    cfg, bridge_ip, username, strict_tls = _resolve_config(args)

    try:
        if args.cmd == "discover":
            bridges = HueClient.discover_bridges()
            if not bridges:
                print("No bridges discovered.")
            for b in bridges:
                print(f"{b.internalipaddress}\t{b.id}")
            return 0

        if args.cmd == "pair":
            ip = _require_bridge_ip(bridge_ip)
            client = HueClient(bridge_ip=ip, insecure_tls=not strict_tls)
            new_user = client.create_user(devicetype=args.devicetype)
            cfg.bridge_ip = ip
            cfg.username = new_user
            if args.strict_tls is not None:
                cfg.strict_tls = bool(args.strict_tls)
            save_config(cfg, args.config)
            print(f"Paired successfully. Saved username to {args.config}")
            return 0

        if args.cmd == "login":
            _config_set(
                cfg,
                args.config,
                bridge_ip=args.bridge_ip,
                username=args.username,
                strict_tls=args.strict_tls,
            )
            print(f"Saved credentials to {args.config}")
            return 0

        if args.cmd == "config":
            if args.config_cmd == "show":
                _print_config(cfg, args.config)
                return 0
            if args.config_cmd == "set":
                _config_set(
                    cfg,
                    args.config,
                    bridge_ip=args.bridge_ip,
                    username=args.username,
                    strict_tls=args.strict_tls,
                )
                print(f"Updated config at {args.config}")
                return 0
            if args.config_cmd == "clear":
                _config_clear(
                    cfg,
                    args.config,
                    clear_bridge_ip=args.bridge_ip,
                    clear_username=args.username,
                    clear_strict_tls=args.clear_strict_tls,
                    clear_all=args.all,
                )
                print(f"Updated config at {args.config}")
                return 0

        ip, user = _require_auth(bridge_ip, username)
        client = HueClient(bridge_ip=ip, username=user, insecure_tls=not strict_tls)

        if args.cmd == "list":
            _print_lights(client)
            return 0
        if args.cmd == "groups":
            _print_groups(client)
            return 0
        if args.cmd == "scenes":
            _print_scenes(client, group=args.group, name_filter=args.name)
            return 0
        if args.cmd == "scene":
            group_id = _resolve_scene_group(client, args.scene_id, args.group)
            client.recall_scene(args.scene_id, group_id)
            print(f"Recalled scene {args.scene_id} on group {group_id}")
            return 0
        if args.cmd == "on":
            _set_on_off(client, args.target, True)
            print("OK")
            return 0
        if args.cmd == "off":
            _set_on_off(client, args.target, False)
            print("OK")
            return 0
        if args.cmd == "toggle":
            _toggle(client, args.target)
            print("OK")
            return 0
        if args.cmd == "brightness":
            _set_brightness(client, args.target, args.value)
            print("OK")
            return 0
        if args.cmd == "tui":
            try:
                from machue.tui import run_tui
            except ModuleNotFoundError as exc:
                raise HueError(
                    "TUI requires curses support. On Windows install with: pip install windows-curses"
                ) from exc
            run_tui(client)
            return 0

        raise HueError(f"Unknown command: {args.cmd}")
    except HueError as exc:
        print(f"Hue error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
