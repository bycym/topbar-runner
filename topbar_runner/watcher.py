"""Small polling watcher for plugin/config edits."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path


class PollingWatcher:
    def __init__(
        self,
        paths: Iterable[Path],
        on_change: Callable[[Path], Awaitable[None]],
        poll_seconds: float = 1,
        debounce_seconds: float = 0.25,
    ) -> None:
        self.paths = list(paths)
        self.on_change = on_change
        self.poll_seconds = poll_seconds
        self.debounce_seconds = debounce_seconds
        self._mtimes = self._snapshot()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_seconds)
            changed = [
                path for path, mtime in self._snapshot().items() if self._mtimes.get(path) != mtime
            ]
            if not changed:
                continue
            self._mtimes = self._snapshot()
            await asyncio.sleep(self.debounce_seconds)
            for path in changed:
                await self.on_change(path)

    def _snapshot(self) -> dict[Path, float | None]:
        return {path: path.stat().st_mtime if path.exists() else None for path in self.paths}
