"""Small cross-platform launch-at-login file hooks."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

APP_ID = "topbar-runner"


def launch_command(config_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "topbar_runner.cli",
        "--config-path",
        str(config_path),
    ]


def set_launch_at_login(
    enabled: bool,
    command: list[str],
    *,
    app_id: str = APP_ID,
    sys_platform: str = sys.platform,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    path = _launch_file_path(app_id, sys_platform=sys_platform, home=home, env=env)
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _launch_file_content(command, app_id=app_id, sys_platform=sys_platform),
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()
    return path


def _launch_file_path(
    app_id: str,
    *,
    sys_platform: str,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    home = home or Path.home()
    env = env or os.environ
    if sys_platform == "darwin":
        return home / "Library" / "LaunchAgents" / f"{app_id}.plist"
    if sys_platform == "win32":
        startup = env.get("APPDATA")
        base = Path(startup) if startup else home / "AppData" / "Roaming"
        return (
            base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{app_id}.bat"
        )
    xdg_config = env.get("XDG_CONFIG_HOME")
    base = Path(xdg_config) if xdg_config else home / ".config"
    return base / "autostart" / f"{app_id}.desktop"


def _launch_file_content(command: list[str], *, app_id: str, sys_platform: str) -> str:
    if sys_platform == "darwin":
        args = "\n".join(f"    <string>{_xml_escape(arg)}</string>" for arg in command)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_xml_escape(app_id)}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
"""
    if sys_platform == "win32":
        return f'@echo off\nstart "" {_cmd_quote(command)}\n'
    return f"""[Desktop Entry]
Type=Application
Name=topbar-runner
Exec={_shell_quote(command)}
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _shell_quote(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _cmd_quote(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)
