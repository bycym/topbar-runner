import sys
from pathlib import Path

from topbar_runner.launch_at_login import launch_command, set_launch_at_login


def test_launch_command_starts_app_with_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    command = launch_command(config_path)

    assert command[1:4] == ["-m", "topbar_runner.cli", "--config-path"]
    assert command[4] == str(config_path)


def test_launch_command_starts_frozen_app_directly(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert launch_command(config_path) == [sys.executable, "--config-path", str(config_path)]


def test_set_launch_at_login_writes_linux_desktop_file(tmp_path: Path) -> None:
    path = set_launch_at_login(
        True,
        ["/bin/topbar-runner", "--config-path", "/tmp/config.toml"],
        sys_platform="linux",
        home=tmp_path,
        env={},
    )

    assert path == tmp_path / ".config" / "autostart" / "topbar-runner.desktop"
    assert "Exec=/bin/topbar-runner --config-path /tmp/config.toml" in path.read_text(
        encoding="utf-8"
    )

    set_launch_at_login(False, [], sys_platform="linux", home=tmp_path, env={})

    assert not path.exists()


def test_set_launch_at_login_writes_macos_plist(tmp_path: Path) -> None:
    path = set_launch_at_login(
        True,
        ["/bin/topbar-runner", "--config-path", "/tmp/config.toml"],
        sys_platform="darwin",
        home=tmp_path,
    )

    content = path.read_text(encoding="utf-8")
    assert path == tmp_path / "Library" / "LaunchAgents" / "topbar-runner.plist"
    assert "<key>ProgramArguments</key>" in content
    assert "<string>/bin/topbar-runner</string>" in content


def test_set_launch_at_login_writes_windows_startup_bat(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"

    path = set_launch_at_login(
        True,
        ["C:/Program Files/topbar-runner/topbar-runner.exe", "--config-path", "C:/cfg.toml"],
        sys_platform="win32",
        home=tmp_path,
        env={"APPDATA": str(appdata)},
    )

    assert path.name == "topbar-runner.bat"
    assert '"C:/Program Files/topbar-runner/topbar-runner.exe"' in path.read_text(encoding="utf-8")
