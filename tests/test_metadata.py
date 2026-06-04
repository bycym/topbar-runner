import shutil
from pathlib import Path

from topbar_runner.filenames import parse_plugin_filename
from topbar_runner.metadata import load_plugin_metadata
from topbar_runner.runner import runtime_from_plugin


def test_load_plugin_metadata() -> None:
    path = Path("tests/fixtures/plugins/bravo.py")

    metadata = load_plugin_metadata(path)

    assert metadata["runtime"]["timeout_seconds"] == 2
    assert metadata["runtime"]["interpreter"] == "/custom/python"
    assert metadata["env"]["ANSWER"] == 42


def test_runtime_from_metadata() -> None:
    plugin = parse_plugin_filename(Path("tests/fixtures/plugins/bravo.py"))
    assert plugin is not None

    runtime = runtime_from_plugin(plugin, Path("/tmp/config.toml"))

    assert runtime.timeout_seconds == 2
    assert runtime.interpreter == "/custom/python"
    assert runtime.extra_env == {"ANSWER": "42"}


def test_shell_runtime_uses_bash(tmp_path: Path) -> None:
    path = tmp_path / "macos_bluetooth_headphone.5m.sh"
    path.write_text("echo hi", encoding="utf-8")
    plugin = parse_plugin_filename(path)
    assert plugin is not None

    runtime = runtime_from_plugin(plugin, Path("/tmp/config.toml"))

    assert runtime.interpreter == (shutil.which("bash") or "/bin/bash")
