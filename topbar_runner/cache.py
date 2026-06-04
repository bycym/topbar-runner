"""Last-good render cache for plugins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from topbar_runner.parser import PluginRender


@dataclass(slots=True)
class CachedRender:
    render: PluginRender
    updated_at: datetime
    stale: bool = False
    error: str | None = None


class RenderCache:
    def __init__(self) -> None:
        self._items: dict[str, CachedRender] = {}

    def set_good(self, plugin_id: str, render: PluginRender) -> CachedRender:
        cached = CachedRender(render=render, updated_at=datetime.now(UTC))
        self._items[plugin_id] = cached
        return cached

    def mark_failed(self, plugin_id: str, error: str) -> CachedRender | None:
        cached = self._items.get(plugin_id)
        if cached is None:
            return None
        cached.stale = True
        cached.error = error
        return cached

    def get(self, plugin_id: str) -> CachedRender | None:
        return self._items.get(plugin_id)
