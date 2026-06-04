from pathlib import Path

from topbar_runner.filenames import (
    apply_plugin_preferences,
    discover_plugins,
    parse_interval,
    parse_plugin_filename,
)


def test_parse_interval() -> None:
    assert parse_interval("5s") == 5
    assert parse_interval("15m") == 900
    assert parse_interval("1h") == 3600
    assert parse_interval("2d") == 172800
    assert parse_interval("daily") is None


def test_parse_plugin_filename() -> None:
    plugin = parse_plugin_filename(Path("tests/fixtures/plugins/alpha.5s.py"))

    assert plugin is not None
    assert plugin.name == "alpha"
    assert plugin.interval_seconds == 5
    assert plugin.kind == "python"


def test_parse_shell_plugin_filename(tmp_path: Path) -> None:
    path = tmp_path / "macos_bluetooth_headphone.5m.sh"
    path.write_text("echo hi", encoding="utf-8")

    plugin = parse_plugin_filename(path)

    assert plugin is not None
    assert plugin.name == "macos_bluetooth_headphone"
    assert plugin.interval_seconds == 300
    assert plugin.kind == "shell"


def test_discover_plugins_ignores_nested_and_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "b.1m.py").write_text("print('b')", encoding="utf-8")
    (tmp_path / "a.5s.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "c.10m.sh").write_text("echo c", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "ignored.1s.py").write_text("print('ignored')", encoding="utf-8")

    plugins = discover_plugins(tmp_path)

    assert [plugin.path.name for plugin in plugins] == ["a.5s.py", "b.1m.py", "c.10m.sh"]


def test_apply_plugin_preferences_filters_and_orders(tmp_path: Path) -> None:
    for name in ["a.5s.py", "b.1m.py", "c.10m.sh"]:
        (tmp_path / name).write_text("print('ok')", encoding="utf-8")
    plugins = discover_plugins(tmp_path)

    configured = apply_plugin_preferences(
        plugins,
        plugin_order=["c.10m.sh"],
        disabled_plugins={"a.5s.py"},
    )

    assert [plugin.path.name for plugin in configured] == ["c.10m.sh", "b.1m.py"]
