from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from topbar_runner.cache import RenderCache
from topbar_runner.filenames import parse_plugin_filename
from topbar_runner.parser import parse_stdout
from topbar_runner.runner import PluginRunner, PluginRuntime, runtime_from_plugin


def test_frozen_app_uses_system_python_for_plugins(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "example.py"
    script.write_text("print('OK')\n", encoding="utf-8")
    plugin = parse_plugin_filename(script)
    assert plugin is not None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        "topbar_runner.runner.shutil.which",
        lambda name: "/usr/bin/python3" if name == "python3" else None,
    )

    runtime = runtime_from_plugin(plugin, tmp_path / "config.toml")

    assert runtime.interpreter == "/usr/bin/python3"


def test_runner_caches_success(tmp_path: Path) -> None:
    asyncio.run(_runner_caches_success(tmp_path))


async def _runner_caches_success(tmp_path: Path) -> None:
    script = tmp_path / "ok.1s.py"
    script.write_text("print('OK')\nprint('Item')\n", encoding="utf-8")
    plugin = parse_plugin_filename(script)
    assert plugin is not None

    result = await PluginRunner().trigger(
        PluginRuntime(plugin=plugin, config_path=tmp_path / "c.toml")
    )

    assert result is not None
    assert result.ok is True
    assert result.cached is not None
    assert result.cached.render.headline is not None
    assert result.cached.render.headline.text == "OK"


def test_runner_uses_plugin_directory_as_cwd(tmp_path: Path) -> None:
    asyncio.run(_runner_uses_plugin_directory_as_cwd(tmp_path))


async def _runner_uses_plugin_directory_as_cwd(tmp_path: Path) -> None:
    script = tmp_path / "cwd.1s.py"
    script.write_text(
        "from pathlib import Path\nprint(Path('cache.txt').read_text())\n",
        encoding="utf-8",
    )
    (tmp_path / "cache.txt").write_text("CWD OK", encoding="utf-8")
    plugin = parse_plugin_filename(script)
    assert plugin is not None

    result = await PluginRunner().trigger(
        PluginRuntime(plugin=plugin, config_path=tmp_path / "c.toml")
    )

    assert result is not None
    assert result.ok is True
    assert result.cached is not None
    assert result.cached.render.headline is not None
    assert result.cached.render.headline.text == "CWD OK"


def test_runner_marks_last_good_stale_on_timeout(tmp_path: Path) -> None:
    asyncio.run(_runner_marks_last_good_stale_on_timeout(tmp_path))


async def _runner_marks_last_good_stale_on_timeout(tmp_path: Path) -> None:
    script = tmp_path / "slow.1s.py"
    script.write_text("import time\nprint('Good')\ntime.sleep(5)\n", encoding="utf-8")
    plugin = parse_plugin_filename(script)
    assert plugin is not None
    cache = RenderCache()
    cache.set_good(str(script), parse_stdout("Good"))

    result = await PluginRunner(cache).trigger(
        PluginRuntime(plugin=plugin, config_path=tmp_path / "c.toml", timeout_seconds=0.01)
    )

    assert result is not None
    assert result.ok is False
    assert result.cached is not None
    assert result.cached.stale is True


def test_runner_coalesces_overlapping_runs(tmp_path: Path) -> None:
    asyncio.run(_runner_coalesces_overlapping_runs(tmp_path))


async def _runner_coalesces_overlapping_runs(tmp_path: Path) -> None:
    counter = tmp_path / "count.txt"
    script = tmp_path / "counter.1s.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import os, time",
                f"p = Path({str(counter)!r})",
                "n = int(p.read_text() or '0') if p.exists() else 0",
                "p.write_text(str(n + 1))",
                "time.sleep(0.05)",
                "print('Count')",
            ]
        ),
        encoding="utf-8",
    )
    plugin = parse_plugin_filename(script)
    assert plugin is not None
    runner = PluginRunner()
    runtime = PluginRuntime(
        plugin=plugin,
        config_path=tmp_path / "c.toml",
        interpreter=sys.executable,
    )

    first = asyncio.create_task(runner.trigger(runtime))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(runner.trigger(runtime))
    await asyncio.gather(first, second)

    assert counter.read_text(encoding="utf-8") == "2"
