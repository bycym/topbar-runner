"""Small TOML app config for local host settings."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # pragma: no cover - Python 3.11+ path
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(slots=True)
class WindowState:
    x: int = 120
    y: int = 80
    width: int = 720
    height: int = 44


@dataclass(slots=True)
class AppConfig:
    plugin_dir: Path | None = None
    theme: str = "dark"
    keep_on_top: bool = True
    launch_at_login: bool = False
    plugin_order: list[str] = field(default_factory=list)
    disabled_plugins: set[str] = field(default_factory=set)
    window: WindowState = field(default_factory=WindowState)


def default_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "topbar-runner" / "config.toml"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "topbar-runner" / "config.toml"
        return Path.home() / "AppData" / "Roaming" / "topbar-runner" / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "topbar-runner" / "config.toml"
    return Path.home() / ".config" / "topbar-runner" / "config.toml"


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    plugin_dir = data.get("plugin_dir")
    window_data = data.get("window", {})
    return AppConfig(
        plugin_dir=Path(plugin_dir).expanduser() if plugin_dir else None,
        theme=_theme_name(str(data.get("theme", "dark"))),
        keep_on_top=bool(data.get("keep_on_top", True)),
        launch_at_login=bool(data.get("launch_at_login", False)),
        plugin_order=_string_list(data.get("plugin_order", [])),
        disabled_plugins=set(_string_list(data.get("disabled_plugins", []))),
        window=WindowState(
            x=int(window_data.get("x", 120)),
            y=int(window_data.get("y", 80)),
            width=int(window_data.get("width", 720)),
            height=int(window_data.get("height", 44)),
        ),
    )


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if config.plugin_dir is not None:
        lines.append(f'plugin_dir = "{_toml_string(str(config.plugin_dir))}"')
    lines.append(f'theme = "{_toml_string(_theme_name(config.theme))}"')
    lines.append(f"keep_on_top = {_toml_bool(config.keep_on_top)}")
    lines.append(f"launch_at_login = {_toml_bool(config.launch_at_login)}")
    lines.append(f"plugin_order = {_toml_array(config.plugin_order)}")
    lines.append(f"disabled_plugins = {_toml_array(sorted(config.disabled_plugins))}")
    lines.append("")
    lines.append("[window]")
    lines.append(f"x = {config.window.x}")
    lines.append(f"y = {config.window.y}")
    lines.append(f"width = {config.window.width}")
    lines.append(f"height = {config.window.height}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(f'"{_toml_string(value)}"' for value in values) + "]"


def _theme_name(value: str) -> str:
    return value if value in {"light", "dark", "synthwave"} else "dark"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (str(item).strip() for item in value) if item]


def config_from_mapping(data: dict[str, Any]) -> AppConfig:
    plugin_dir = data.get("plugin_dir")
    return AppConfig(
        plugin_dir=Path(plugin_dir) if plugin_dir else None,
        plugin_order=_string_list(data.get("plugin_order", [])),
        disabled_plugins=set(_string_list(data.get("disabled_plugins", []))),
    )
