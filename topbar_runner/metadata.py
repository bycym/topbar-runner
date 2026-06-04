"""Optional commented TOML metadata extraction for plugin files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no cover - Python 3.11+ path
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

START = "# /// topbar-runner"
END = "# ///"


def load_plugin_metadata(path: Path) -> dict[str, Any]:
    """Load optional commented TOML block near the top of a plugin file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_block = False
    toml_lines: list[str] = []

    for raw_line in lines[:80]:
        stripped = raw_line.strip()
        if stripped == START:
            in_block = True
            continue
        if in_block and stripped == END:
            break
        if in_block:
            toml_lines.append(raw_line[1:].lstrip() if raw_line.startswith("#") else raw_line)

    if not toml_lines:
        return {}
    data = tomllib.loads("\n".join(toml_lines))
    return data if isinstance(data, dict) else {}
