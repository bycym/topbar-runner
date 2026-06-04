"""Plugin filename discovery and xbar-style interval parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_INTERVAL_RE = re.compile(r"(?P<value>\d+)(?P<unit>s|m|h|d)$", re.IGNORECASE)
_SUPPORTED_SUFFIXES = {".py", ".pyw", ".sh"}


@dataclass(frozen=True, slots=True)
class PluginFile:
    path: Path
    name: str
    interval_seconds: int
    kind: str


def parse_interval(token: str) -> int | None:
    """Parse xbar filename interval token such as 5s, 15m, or 1h."""
    match = _INTERVAL_RE.fullmatch(token.strip())
    if not match:
        return None
    value = int(match.group("value"))
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group("unit").lower()]
    return value * multiplier


def parse_plugin_filename(path: Path, default_interval_seconds: int = 60) -> PluginFile | None:
    """Return plugin metadata for a direct xbar-style plugin file."""
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES or not path.is_file():
        return None

    stem_parts = path.stem.split(".")
    interval = default_interval_seconds
    name_parts = stem_parts
    if stem_parts:
        parsed = parse_interval(stem_parts[-1])
        if parsed is not None:
            interval = parsed
            name_parts = stem_parts[:-1] or stem_parts

    kind = "python" if suffix in {".py", ".pyw"} else "shell"
    return PluginFile(path=path, name=".".join(name_parts), interval_seconds=interval, kind=kind)


def discover_plugins(plugin_root: Path, default_interval_seconds: int = 60) -> list[PluginFile]:
    """Discover only direct child supported plugin files in lexical filename order."""
    if not plugin_root.exists() or not plugin_root.is_dir():
        return []

    plugins = [
        parsed
        for child in sorted(plugin_root.iterdir(), key=lambda item: item.name.lower())
        if (parsed := parse_plugin_filename(child, default_interval_seconds)) is not None
    ]
    return plugins


def apply_plugin_preferences(
    plugins: list[PluginFile],
    plugin_order: list[str],
    disabled_plugins: set[str],
) -> list[PluginFile]:
    """Filter disabled plugins and apply local filename ordering."""
    order = {name: index for index, name in enumerate(plugin_order)}
    enabled = [plugin for plugin in plugins if plugin.path.name not in disabled_plugins]
    return sorted(
        enabled,
        key=lambda plugin: (
            order.get(plugin.path.name, len(order)),
            plugin.path.name.lower(),
        ),
    )
