"""Interval scheduler for plugin runtimes."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from topbar_runner.runner import PluginRunner, PluginRuntime


class IntervalScheduler:
    def __init__(self, runner: PluginRunner) -> None:
        self.runner = runner
        self._tasks: list[asyncio.Task[None]] = []

    def start(self, runtimes: Iterable[PluginRuntime]) -> None:
        self.stop()
        self._tasks = [asyncio.create_task(self._loop(runtime)) for runtime in runtimes]

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks = []

    async def _loop(self, runtime: PluginRuntime) -> None:
        await self.runner.trigger(runtime, "startup")
        while True:
            await asyncio.sleep(runtime.plugin.interval_seconds)
            await self.runner.trigger(runtime, "interval")
