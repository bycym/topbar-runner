"""Async plugin process runner with no-overlap and coalesced reruns."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from topbar_runner.cache import CachedRender, RenderCache
from topbar_runner.filenames import PluginFile
from topbar_runner.logging import get_logger
from topbar_runner.metadata import load_plugin_metadata
from topbar_runner.parser import parse_stdout


@dataclass(slots=True)
class RunResult:
    plugin: PluginFile
    cached: CachedRender | None
    ok: bool
    error: str | None = None


@dataclass(slots=True)
class PluginRuntime:
    plugin: PluginFile
    config_path: Path
    timeout_seconds: float = 10
    interpreter: str = sys.executable
    extra_env: dict[str, str] = field(default_factory=dict)


class PluginRunner:
    def __init__(
        self,
        cache: RenderCache | None = None,
        on_result: Callable[[RunResult], None] | None = None,
    ) -> None:
        self.cache = cache or RenderCache()
        self.on_result = on_result
        self._running: dict[Path, asyncio.Task[RunResult]] = {}
        self._pending: set[Path] = set()

    async def trigger(self, runtime: PluginRuntime, reason: str = "manual") -> RunResult | None:
        """Run plugin, or coalesce one pending rerun if already active."""
        path = runtime.plugin.path
        if path in self._running:
            get_logger().debug("plugin run coalesced: %s reason=%s", path, reason)
            self._pending.add(path)
            return None

        task = asyncio.create_task(self._run_until_settled(runtime, reason))
        self._running[path] = task
        try:
            return await task
        finally:
            self._running.pop(path, None)

    async def _run_until_settled(self, runtime: PluginRuntime, reason: str) -> RunResult:
        result = await self._run_once(runtime, reason)
        while runtime.plugin.path in self._pending:
            self._pending.remove(runtime.plugin.path)
            result = await self._run_once(runtime, "coalesced")
        return result

    async def _run_once(self, runtime: PluginRuntime, reason: str) -> RunResult:
        env = self._env(runtime, reason)
        proc: asyncio.subprocess.Process | None = None
        plugin_path = runtime.plugin.path.resolve()
        plugin_dir = runtime.plugin.path.parent.resolve()
        get_logger().debug(
            "plugin run starting: path=%s interpreter=%s cwd=%s reason=%s timeout=%ss",
            plugin_path,
            runtime.interpreter,
            plugin_dir,
            reason,
            runtime.timeout_seconds,
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                runtime.interpreter,
                str(plugin_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=plugin_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=runtime.timeout_seconds,
            )
        except TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.wait()
            return self._failure(runtime, f"timeout after {runtime.timeout_seconds:g}s")
        except OSError as exc:
            return self._failure(runtime, f"failed to start: {exc}")

        if proc.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            return self._failure(runtime, f"exit {proc.returncode}: {message}")

        render = parse_stdout(stdout.decode("utf-8", errors="replace"))
        cached = self.cache.set_good(str(runtime.plugin.path), render)
        result = RunResult(plugin=runtime.plugin, cached=cached, ok=True)
        get_logger().info(
            "plugin run succeeded: %s stdout_bytes=%d menu_items=%d headline=%r",
            runtime.plugin.path,
            len(stdout),
            len(render.menu_items),
            render.headline.text if render.headline is not None else None,
        )
        self._emit(result)
        return result

    def _failure(self, runtime: PluginRuntime, error: str) -> RunResult:
        cached = self.cache.mark_failed(str(runtime.plugin.path), error)
        result = RunResult(plugin=runtime.plugin, cached=cached, ok=False, error=error)
        get_logger().warning("plugin run failed: %s: %s", runtime.plugin.path, error)
        self._emit(result)
        return result

    def _emit(self, result: RunResult) -> None:
        if self.on_result is not None:
            self.on_result(result)

    @staticmethod
    def _env(runtime: PluginRuntime, reason: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(runtime.extra_env)
        env.update(
            {
                "TOPBAR_RUNNER_REASON": reason,
                "TOPBAR_RUNNER_PLUGIN_PATH": str(runtime.plugin.path.resolve()),
                "TOPBAR_RUNNER_PLUGIN_DIR": str(runtime.plugin.path.parent.resolve()),
                "TOPBAR_RUNNER_CONFIG_PATH": str(runtime.config_path),
                "TOPBAR_RUNNER_HOST_OS": sys.platform,
            }
        )
        return env


def runtime_from_plugin(plugin: PluginFile, config_path: Path) -> PluginRuntime:
    metadata = load_plugin_metadata(plugin.path)
    runtime = metadata.get("runtime", {}) if isinstance(metadata.get("runtime"), dict) else {}
    env = metadata.get("env", {}) if isinstance(metadata.get("env"), dict) else {}
    default_interpreter = _default_interpreter(plugin)
    return PluginRuntime(
        plugin=plugin,
        config_path=config_path,
        timeout_seconds=float(runtime.get("timeout_seconds", 10)),
        interpreter=str(runtime.get("interpreter", default_interpreter)),
        extra_env={str(key): str(value) for key, value in env.items()},
    )


def _default_interpreter(plugin: PluginFile) -> str:
    if plugin.kind == "shell":
        return shutil.which("bash") or "/bin/bash"
    return sys.executable
