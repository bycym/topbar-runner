"""Permissive parser for the xbar/BitBar text DSL."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field

SEPARATOR = "---"


@dataclass(slots=True)
class MenuItem:
    text: str
    attrs: dict[str, str | bool] = field(default_factory=dict)
    depth: int = 0
    is_separator: bool = False
    children: list[MenuItem] = field(default_factory=list)

    @property
    def dropdown(self) -> bool:
        value = self.attrs.get("dropdown")
        return value is not False and value != "false"

    @property
    def alternate(self) -> bool:
        value = self.attrs.get("alternate")
        return value is True or value == "true"


@dataclass(slots=True)
class PluginRender:
    headline: MenuItem | None
    menu_items: list[MenuItem]
    extra_chips: list[MenuItem]
    raw_output: str
    errors: list[str] = field(default_factory=list)


def _coerce_attr(value: str) -> str | bool:
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    return value


def _parse_attrs(raw: str) -> tuple[str, dict[str, str | bool], list[str]]:
    if "|" not in raw:
        return raw.rstrip(), {}, []

    label, attr_text = raw.split("|", 1)
    attrs: dict[str, str | bool] = {}
    errors: list[str] = []
    try:
        tokens = shlex.split(attr_text, posix=True)
    except ValueError as exc:
        return label.rstrip(), {}, [f"malformed attrs: {exc}"]

    for token in tokens:
        if "=" not in token:
            attrs[token] = True
            continue
        key, value = token.split("=", 1)
        if key:
            attrs[key] = _coerce_attr(value)
    return label.rstrip(), attrs, errors


def parse_stdout(output: str) -> PluginRender:
    """Parse plugin stdout without failing the whole plugin on bad lines."""
    lines = output.splitlines()
    errors: list[str] = []
    headline = _parse_line(lines[0], 0, errors) if lines else None
    menu_roots: list[MenuItem] = []
    stack: list[MenuItem] = []
    extra_chips: list[MenuItem] = []

    for raw in lines[1:]:
        item = _parse_line(raw, 0, errors)
        if item is None:
            continue
        if item.is_separator:
            stack.clear()
            continue
        if item.depth == 0 and not item.dropdown:
            extra_chips.append(item)
            continue

        while stack and stack[-1].depth >= item.depth:
            stack.pop()
        if stack:
            stack[-1].children.append(item)
        else:
            menu_roots.append(item)
        stack.append(item)

    return PluginRender(
        headline=headline,
        menu_items=menu_roots,
        extra_chips=extra_chips,
        raw_output=output,
        errors=errors,
    )


def _parse_line(raw: str, _line_no: int, errors: list[str]) -> MenuItem | None:
    stripped = raw.strip()
    if not stripped:
        return None
    if stripped == SEPARATOR:
        return MenuItem(text="", is_separator=True)

    depth = 0
    content = raw
    while content.startswith("--"):
        depth += 1
        content = content[2:]
    content = content.lstrip()
    if content.strip() == SEPARATOR:
        return MenuItem(text="", depth=depth, is_separator=True)

    text, attrs, attr_errors = _parse_attrs(content)
    errors.extend(attr_errors)
    return MenuItem(text=text, attrs=attrs, depth=depth)
