from pathlib import Path

from topbar_runner.app_config import (
    AppConfig,
    WindowState,
    default_config_path,
    load_config,
    save_config,
)


def test_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config = AppConfig(
        plugin_dir=Path("/tmp/plugins"),
        theme="synthwave",
        keep_on_top=False,
        launch_at_login=True,
        plugin_order=["z.1s.py", "a.1s.py"],
        disabled_plugins={"off.1s.py"},
        window=WindowState(x=1, y=2, width=300, height=40),
    )

    save_config(path, config)
    loaded = load_config(path)

    assert loaded.plugin_dir == Path("/tmp/plugins")
    assert loaded.theme == "synthwave"
    assert loaded.keep_on_top is False
    assert loaded.launch_at_login is True
    assert loaded.plugin_order == ["z.1s.py", "a.1s.py"]
    assert loaded.disabled_plugins == {"off.1s.py"}
    assert loaded.window.width == 300


def test_unknown_theme_falls_back_to_dark(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('theme = "unknown"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.theme == "dark"


def test_default_config_path_uses_xdg_config_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert default_config_path() == tmp_path / "topbar-runner" / "config.toml"
