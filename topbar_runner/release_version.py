"""Choose release tags for the GitHub Actions workflow."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

MANUAL_TAG_PATTERN = re.compile(r"v[0-9][0-9A-Za-z._-]*")
NUMERIC_TAG_PATTERN = re.compile(r"v[0-9]+(?:\.[0-9]+)*")
FIRST_RELEASE_TAG = "v0.1.0"


def select_release_tag(manual_tag: str, tags: list[str]) -> str:
    """Use a manual tag or advance the highest numeric tag."""
    if manual_tag:
        if not MANUAL_TAG_PATTERN.fullmatch(manual_tag):
            raise ValueError("release_tag must be a version tag such as v2 or v0.1.0")
        return manual_tag

    numeric_tags = [
        tuple(int(part) for part in tag[1:].split("."))
        for tag in tags
        if NUMERIC_TAG_PATTERN.fullmatch(tag)
    ]
    if not numeric_tags:
        return FIRST_RELEASE_TAG
    version = list(max(numeric_tags))
    if len(version) == 1:
        version.append(1)
    else:
        version[-1] += 1
    return "v" + ".".join(str(part) for part in version)


def main() -> None:
    tags = subprocess.check_output(["git", "tag", "--list"], text=True).splitlines()
    tag = select_release_tag(os.environ.get("RELEASE_TAG", ""), tags)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"release_tag={tag}\n")
    print(f"Release tag: {tag}")


if __name__ == "__main__":
    main()
