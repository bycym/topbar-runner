"""Safe action helpers shared by CLI and UI hosts."""

from __future__ import annotations

from urllib.parse import urlparse

ALLOWED_HREF_SCHEMES = {"http", "https", "mailto"}


def is_allowed_href(href: str) -> bool:
    parsed = urlparse(href)
    return parsed.scheme in ALLOWED_HREF_SCHEMES and bool(parsed.geturl())
