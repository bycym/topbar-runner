from pathlib import Path

import topbar_runner.ui
from topbar_runner.app_config import default_config_path
from topbar_runner.cli import dev_main, run_app_cli, run_cli


def test_dev_cli_console_mode_runs_sample_plugins(capsys) -> None:
    exit_code = dev_main(["--console"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "hello.5s.py: Hello" in output


def test_cli_reports_missing_plugins(tmp_path: Path, capsys) -> None:
    exit_code = run_cli(["--plugin-dir", str(tmp_path)])

    assert exit_code == 1
    assert "No plugins found" in capsys.readouterr().out


def test_app_cli_console_accepts_relative_plugin_dir(capsys) -> None:
    exit_code = run_app_cli(["--console", "--plugin-dir", "examples/plugins"])

    assert exit_code == 0
    assert "hello.5s.py: Hello" in capsys.readouterr().out


def test_cli_debug_writes_log_and_stderr(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "debug.log"

    exit_code = run_cli(
        [
            "--debug",
            "--plugin-dir",
            "examples/plugins",
            "--log-path",
            str(log_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "cli starting" in captured.err
    assert "plugin run starting" in log_path.read_text(encoding="utf-8")


def test_app_cli_passes_debug_to_ui(monkeypatch, tmp_path: Path) -> None:
    calls = []
    log_path = tmp_path / "ui.log"

    def fake_run_app(config_path, plugin_dir=None, log_path=None, debug=False):
        calls.append((config_path, plugin_dir, log_path, debug))
        return 0

    monkeypatch.setattr(topbar_runner.ui, "run_app", fake_run_app)

    exit_code = run_app_cli(
        [
            "--debug",
            "--plugin-dir",
            "examples/plugins",
            "--log-path",
            str(log_path),
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            default_config_path(),
            Path("examples/plugins"),
            log_path,
            True,
        )
    ]


def test_app_cli_uses_config_based_log_by_default(monkeypatch, tmp_path: Path) -> None:
    calls = []
    config_path = tmp_path / "config.toml"

    def fake_run_app(config_path, plugin_dir=None, log_path=None, debug=False):
        calls.append((config_path, log_path))
        return 0

    monkeypatch.setattr(topbar_runner.ui, "run_app", fake_run_app)

    assert run_app_cli(["--config-path", str(config_path)]) == 0
    assert calls == [(config_path, None)]
