from __future__ import annotations

import argparse
import curses
import time
from pathlib import Path

from machue.config import DEFAULT_CONFIG_PATH, load_config
from machue.hue import HueClient, HueError


class HueTUI:
    DEFAULT_SPLIT_RATIO = 0.60

    def __init__(self, client: HueClient):
        self.client = client
        self.mode = "lights"
        self.selected_light_index = 0
        self.selected_scene_index = 0
        self.light_scroll = 0
        self.scene_scroll = 0
        self.light_rows: list[tuple[str, dict]] = []
        self.scene_rows: list[tuple[str, dict]] = []
        self.group_names: dict[str, str] = {}
        self.status = ""
        self.last_refresh = 0.0
        self.last_width = 0
        self.colors_enabled = False
        self.panel_split_ratio = self.DEFAULT_SPLIT_RATIO

        self.attr_title = curses.A_BOLD
        self.attr_header = curses.A_UNDERLINE | curses.A_BOLD
        self.attr_selected = curses.A_REVERSE | curses.A_BOLD
        self.attr_on = curses.A_BOLD
        self.attr_off = curses.A_DIM
        self.attr_tab_active = curses.A_BOLD
        self.attr_tab_inactive = curses.A_DIM

    def _init_theme(self) -> None:
        if not curses.has_colors():
            return
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass

        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)   # selected row
        curses.init_pair(2, curses.COLOR_GREEN, -1)                   # light on
        curses.init_pair(3, curses.COLOR_RED, -1)                     # light off
        curses.init_pair(4, curses.COLOR_CYAN, -1)                    # active tab
        curses.init_pair(5, curses.COLOR_WHITE, -1)                   # title/header

        self.colors_enabled = True
        self.attr_title = curses.color_pair(5) | curses.A_BOLD
        self.attr_header = curses.color_pair(5) | curses.A_BOLD
        self.attr_selected = curses.color_pair(1) | curses.A_BOLD
        self.attr_on = curses.color_pair(2) | curses.A_BOLD
        self.attr_off = curses.color_pair(3) | curses.A_DIM
        self.attr_tab_active = curses.color_pair(4) | curses.A_BOLD
        self.attr_tab_inactive = curses.A_DIM

    def _selected_index(self) -> int:
        if self.mode == "lights":
            return self.selected_light_index
        return self.selected_scene_index

    def _set_selected_index(self, value: int) -> None:
        if self.mode == "lights":
            self.selected_light_index = value
            return
        self.selected_scene_index = value

    def _active_rows(self) -> list[tuple[str, dict]]:
        if self.mode == "lights":
            return self.light_rows
        return self.scene_rows

    def _active_scroll(self) -> int:
        if self.mode == "lights":
            return self.light_scroll
        return self.scene_scroll

    def _set_active_scroll(self, value: int) -> None:
        if self.mode == "lights":
            self.light_scroll = value
            return
        self.scene_scroll = value

    @staticmethod
    def _safe_addnstr(stdscr: curses.window, y: int, x: int, text: str, max_chars: int, attr: int = 0) -> None:
        if max_chars <= 0:
            return
        try:
            stdscr.addnstr(y, x, text, max_chars, attr)
        except curses.error:
            pass

    def _ensure_selection_visible(self, visible_rows: int) -> None:
        rows = self._active_rows()
        if not rows:
            self._set_active_scroll(0)
            return

        idx = max(0, min(self._selected_index(), len(rows) - 1))
        self._set_selected_index(idx)

        scroll = self._active_scroll()
        if idx < scroll:
            scroll = idx
        elif idx >= scroll + visible_rows:
            scroll = idx - visible_rows + 1

        max_scroll = max(0, len(rows) - visible_rows)
        scroll = max(0, min(scroll, max_scroll))
        self._set_active_scroll(scroll)

    def _move_selection(self, delta: int) -> None:
        rows = self._active_rows()
        if not rows:
            return
        next_index = max(0, min(len(rows) - 1, self._selected_index() + delta))
        self._set_selected_index(next_index)

    def _jump_selection(self, end: bool) -> None:
        rows = self._active_rows()
        if not rows:
            return
        self._set_selected_index(len(rows) - 1 if end else 0)

    def load_lights(self) -> None:
        lights = self.client.get_lights()
        self.light_rows = sorted(lights.items(), key=lambda kv: int(kv[0]))
        if self.selected_light_index >= len(self.light_rows):
            self.selected_light_index = max(0, len(self.light_rows) - 1)
        self.light_scroll = min(self.light_scroll, max(0, len(self.light_rows) - 1))

    def load_scenes(self) -> None:
        scenes = self.client.get_scenes()
        groups = self.client.get_groups()
        self.group_names = {gid: str(g.get("name", f"Group {gid}")) for gid, g in groups.items()}
        self.scene_rows = sorted(
            scenes.items(),
            key=lambda kv: (str(kv[1].get("name", "")).lower(), kv[0]),
        )
        if self.selected_scene_index >= len(self.scene_rows):
            self.selected_scene_index = max(0, len(self.scene_rows) - 1)
        self.scene_scroll = min(self.scene_scroll, max(0, len(self.scene_rows) - 1))

    def load_all(self) -> None:
        self.load_lights()
        self.load_scenes()
        self.last_refresh = time.time()

    def set_status(self, text: str) -> None:
        self.status = text

    def toggle_selected(self) -> None:
        if not self.light_rows:
            return
        light_id, light = self.light_rows[self.selected_light_index]
        current = bool(light.get("state", {}).get("on", False))
        self.client.set_light_state(light_id, {"on": not current})
        self.set_status(f"Toggled {light.get('name', light_id)}")
        self.load_lights()

    def change_brightness_selected(self, delta: int) -> None:
        if not self.light_rows:
            return
        light_id, light = self.light_rows[self.selected_light_index]
        state = light.get("state", {})
        current = int(state.get("bri", 1))
        target = max(1, min(254, current + delta))
        self.client.set_light_state(light_id, {"on": True, "bri": target})
        self.set_status(f"Brightness {target} for {light.get('name', light_id)}")
        self.load_lights()

    def recall_selected_scene(self) -> None:
        if not self.scene_rows:
            return
        scene_id, scene = self.scene_rows[self.selected_scene_index]
        group_raw = scene.get("group")
        if group_raw is None:
            group_id = 0
        else:
            try:
                group_id = int(str(group_raw))
            except ValueError as exc:
                raise HueError(f"Scene {scene_id} has invalid group: {group_raw}") from exc
        self.client.recall_scene(scene_id, group_id)
        self.set_status(f"Scene {scene.get('name', scene_id)} recalled")
        self.load_lights()

    def switch_mode(self) -> None:
        self.mode = "scenes" if self.mode == "lights" else "lights"
        self.set_status(f"Mode: {self.mode}")

    def _compute_panel_widths(self, total_width: int) -> tuple[int, int]:
        # Exclude divider and one-column gap so the ratio applies to usable content width.
        usable_width = max(1, total_width - 2)
        min_list = 40
        min_detail = 28
        max_list = max(min_list, usable_width - min_detail)
        list_w = int(round(usable_width * self.panel_split_ratio))
        list_w = max(min_list, min(max_list, list_w))
        panel_w = usable_width - list_w
        return list_w, panel_w

    def adjust_panel_split(self, delta: float) -> None:
        if self.last_width < 100:
            self.set_status("Split resize requires wider terminal (>=100 cols)")
            return

        usable_width = max(1, self.last_width - 2)
        min_list = 40
        min_detail = 28
        max_list = max(min_list, usable_width - min_detail)
        min_ratio = min_list / usable_width
        max_ratio = max_list / usable_width

        self.panel_split_ratio = max(min_ratio, min(max_ratio, self.panel_split_ratio + delta))
        left_pct = int(round(self.panel_split_ratio * 100))
        self.set_status(f"Panel split: {left_pct}/{100 - left_pct}")

    def reset_panel_split(self) -> None:
        self.panel_split_ratio = self.DEFAULT_SPLIT_RATIO
        self.set_status("Panel split reset to 60/40")

    def _draw_tabs(self, stdscr: curses.window, width: int) -> None:
        lights_label = f"[1] Lights ({len(self.light_rows)})"
        scenes_label = f"[2] Scenes ({len(self.scene_rows)})"
        if self.mode == "lights":
            left_attr = self.attr_tab_active
            right_attr = self.attr_tab_inactive
        else:
            left_attr = self.attr_tab_inactive
            right_attr = self.attr_tab_active

        self._safe_addnstr(stdscr, 1, 0, lights_label, width, left_attr)
        self._safe_addnstr(stdscr, 1, len(lights_label) + 2, scenes_label, width - len(lights_label) - 2, right_attr)

        try:
            stdscr.hline(2, 0, curses.ACS_HLINE, max(1, width - 1))
        except curses.error:
            pass

    @staticmethod
    def _brightness_bar(bri: int, width: int) -> str:
        width = max(8, width)
        fill = int((bri / 254.0) * width)
        fill = max(0, min(width, fill))
        return "[" + ("#" * fill) + ("-" * (width - fill)) + "]"

    def _draw_details(self, stdscr: curses.window, x: int, y_top: int, y_bottom: int, width: int) -> None:
        if width < 20 or y_bottom < y_top:
            return

        self._safe_addnstr(stdscr, y_top, x, "Details", width, self.attr_header)
        rows = self._active_rows()
        if not rows:
            self._safe_addnstr(stdscr, y_top + 2, x, "No items", width, curses.A_DIM)
            return

        idx = self._selected_index()
        idx = max(0, min(idx, len(rows) - 1))
        key, item = rows[idx]
        lines: list[str] = []

        if self.mode == "lights":
            state = item.get("state", {})
            name = str(item.get("name", "Unnamed"))
            is_on = bool(state.get("on", False))
            bri = int(state.get("bri", 1))
            bar = self._brightness_bar(bri, min(24, max(10, width - 8)))

            lines = [
                f"Name: {name}",
                f"ID: {key}",
                f"State: {'ON' if is_on else 'OFF'}",
                f"Brightness: {bri}/254",
                bar,
                "",
                "Actions:",
                "Enter/Space: Toggle",
                "+ / -: Brightness",
            ]
        else:
            name = str(item.get("name", "Unnamed"))
            group_raw = item.get("group")
            if group_raw is None:
                group_name = "All lights (0)"
            else:
                group_name = self.group_names.get(str(group_raw), f"Group {group_raw}")
            scene_type = str(item.get("type", "-"))

            lines = [
                f"Name: {name}",
                f"Scene ID: {key}",
                f"Group: {group_name}",
                f"Type: {scene_type}",
                "",
                "Actions:",
                "Enter/Space: Recall scene",
            ]

        y = y_top + 2
        for line in lines:
            if y > y_bottom:
                break
            self._safe_addnstr(stdscr, y, x, line, width, curses.A_NORMAL)
            y += 1

    def _draw_table(self, stdscr: curses.window, x: int, y_top: int, y_bottom: int, width: int) -> None:
        if y_bottom < y_top or width < 24:
            return

        rows = self._active_rows()
        row_start = y_top + 1
        visible_rows = max(1, y_bottom - row_start + 1)
        self._ensure_selection_visible(visible_rows)
        scroll = self._active_scroll()
        selected_index = self._selected_index()

        if self.mode == "lights":
            id_w = 4
            state_w = 5
            bri_w = 5
            name_w = max(8, width - id_w - state_w - bri_w - 4)
            header = f"{'ID':>2}  {'Name':<{name_w}} {'State':<5} {'Bri':<3}"
            self._safe_addnstr(stdscr, y_top, x, header, width, self.attr_header)

            end = min(len(rows), scroll + visible_rows)
            for draw_idx, row_idx in enumerate(range(scroll, end)):
                y = row_start + draw_idx
                light_id, light = rows[row_idx]
                is_on = bool(light.get("state", {}).get("on", False))
                bri = str(light.get("state", {}).get("bri", "-"))
                name = str(light.get("name", "Unnamed"))[:name_w]
                state = "ON" if is_on else "OFF"
                line = f"{light_id:>2}  {name:<{name_w}} {state:<5} {bri:<3}"

                if row_idx == selected_index:
                    attr = self.attr_selected
                else:
                    attr = self.attr_on if is_on else self.attr_off
                self._safe_addnstr(stdscr, y, x, line, width, attr)
        else:
            idx_w = 4
            group_w = min(20, max(10, int(width * 0.32)))
            name_w = max(8, width - idx_w - group_w - 3)
            header = f"{'#':>{idx_w}} {'Name':<{name_w}} {'Group':<{group_w}}"
            self._safe_addnstr(stdscr, y_top, x, header, width, self.attr_header)

            end = min(len(rows), scroll + visible_rows)
            for draw_idx, row_idx in enumerate(range(scroll, end)):
                y = row_start + draw_idx
                _, scene = rows[row_idx]
                name = str(scene.get("name", "Unnamed"))[:name_w]
                group_raw = scene.get("group")
                if group_raw is None:
                    group_name = "All lights"
                else:
                    group_name = self.group_names.get(str(group_raw), f"Group {group_raw}")
                group_name = group_name[:group_w]
                row_num = row_idx + 1
                line = f"{row_num:>{idx_w}} {name:<{name_w}} {group_name:<{group_w}}"
                attr = self.attr_selected if row_idx == selected_index else curses.A_NORMAL
                self._safe_addnstr(stdscr, y, x, line, width, attr)

        if not rows:
            empty_msg = "No lights found." if self.mode == "lights" else "No scenes found."
            self._safe_addnstr(stdscr, y_top + 2, x, empty_msg, width, curses.A_DIM)

    def draw(self, stdscr: curses.window) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        self.last_width = w
        if h < 10 or w < 52:
            self._safe_addnstr(
                stdscr,
                0,
                0,
                "Terminal window too small. Resize to at least 52x10.",
                max(1, w - 1),
                self.attr_title,
            )
            stdscr.refresh()
            return

        self._safe_addnstr(stdscr, 0, 0, "MacHue TUI", w - 1, self.attr_title)
        self._draw_tabs(stdscr, w)

        content_top = 3
        footer_top = h - 2
        content_bottom = footer_top - 1

        show_panel = w >= 100
        list_w = 0
        if show_panel:
            list_w, panel_w = self._compute_panel_widths(w)
            panel_x = list_w + 1

            try:
                for y in range(content_top, footer_top):
                    stdscr.addch(y, list_w, curses.ACS_VLINE)
            except curses.error:
                pass

            self._draw_table(stdscr, 0, content_top, content_bottom, list_w - 1)
            self._draw_details(stdscr, panel_x, content_top, content_bottom, panel_w)
        else:
            self._draw_table(stdscr, 0, content_top, content_bottom, w - 1)

        active_rows = self._active_rows()
        selected = min(self._selected_index() + 1, len(active_rows)) if active_rows else 0
        status_line = self.status or "Ready"
        status_line = (
            f"{status_line} | {self.mode.upper()} {selected}/{len(active_rows)}"
            f" | L:{len(self.light_rows)} S:{len(self.scene_rows)}"
        )
        if show_panel:
            left_pct = int(round((list_w / w) * 100))
            status_line += f" | Split {left_pct}/{100 - left_pct}"
        hints = "↑/↓ move  PgUp/PgDn page  g/G top/bottom  Tab/←→ mode  [ ] resize  0 reset  Enter action  +/- bri  r refresh  q quit"
        self._safe_addnstr(stdscr, h - 2, 0, status_line, w - 1, curses.A_DIM)
        self._safe_addnstr(stdscr, h - 1, 0, hints, w - 1, curses.A_DIM)
        stdscr.refresh()

    def run(self, stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        self._init_theme()
        stdscr.timeout(250)
        try:
            self.load_all()
        except HueError as exc:
            self.set_status(str(exc))
        while True:
            now = time.time()
            if now - self.last_refresh > 5:
                try:
                    self.load_all()
                except HueError as exc:
                    self.set_status(str(exc))
            self.draw(stdscr)
            key = stdscr.getch()
            if key == -1:
                continue
            if key in (ord("q"), 27):
                break
            try:
                if key == curses.KEY_RESIZE:
                    continue
                if key in (curses.KEY_UP, ord("k")):
                    self._move_selection(-1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    self._move_selection(1)
                elif key == curses.KEY_PPAGE:
                    self._move_selection(-10)
                elif key == curses.KEY_NPAGE:
                    self._move_selection(10)
                elif key == curses.KEY_HOME or key == ord("g"):
                    self._jump_selection(end=False)
                elif key == curses.KEY_END or key == ord("G"):
                    self._jump_selection(end=True)
                elif key in (ord("\n"), ord(" ")):
                    if self.mode == "lights":
                        self.toggle_selected()
                    else:
                        self.recall_selected_scene()
                elif key in (ord("+"), ord("=")):
                    if self.mode == "lights":
                        self.change_brightness_selected(25)
                elif key == ord("-"):
                    if self.mode == "lights":
                        self.change_brightness_selected(-25)
                elif key == ord("r"):
                    self.load_all()
                    self.set_status("Refreshed")
                elif key == ord("["):
                    self.adjust_panel_split(-0.03)
                elif key == ord("]"):
                    self.adjust_panel_split(0.03)
                elif key == ord("0"):
                    self.reset_panel_split()
                elif key in (ord("\t"), curses.KEY_LEFT, curses.KEY_RIGHT):
                    if key == curses.KEY_LEFT:
                        self.mode = "lights"
                    elif key == curses.KEY_RIGHT:
                        self.mode = "scenes"
                    else:
                        self.switch_mode()
                    self.set_status(f"Mode: {self.mode}")
                elif key == ord("1"):
                    self.mode = "lights"
                    self.set_status("Mode: lights")
                elif key == ord("2"):
                    self.mode = "scenes"
                    self.set_status("Mode: scenes")
                elif key == ord("l"):
                    self.mode = "lights"
                    self.set_status("Mode: lights")
                elif key == ord("s"):
                    self.mode = "scenes"
                    self.set_status("Mode: scenes")
            except HueError as exc:
                self.set_status(str(exc))


def run_tui(client: HueClient) -> None:
    app = HueTUI(client)
    curses.wrapper(app.run)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MacHue TUI")
    p.add_argument("--bridge-ip", help="Hue bridge IP")
    p.add_argument("--username", help="Hue API username/token")
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
    p.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})",
    )
    return p


def main() -> int:
    args = _parser().parse_args()
    cfg = load_config(args.config)
    bridge_ip = args.bridge_ip or cfg.bridge_ip
    username = args.username or cfg.username
    if args.strict_tls is None:
        strict_tls = bool(cfg.strict_tls)
    else:
        strict_tls = bool(args.strict_tls)
    if not bridge_ip or not username:
        print("Missing bridge_ip/username. Use --bridge-ip --username or run pair in CLI first.")
        return 2
    client = HueClient(bridge_ip=bridge_ip, username=username, insecure_tls=not strict_tls)
    try:
        run_tui(client)
    except HueError as exc:
        print(f"Hue error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
