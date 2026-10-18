import pytest

from topbar_runner.release_version import select_release_tag


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ([], "v0.1.0"),
        (["v0.1.0"], "v0.1.1"),
        (["v1.3", "v2"], "v2.1"),
        (["v1.9", "v1.10"], "v1.11"),
        (["v2-beta", "v1.3"], "v1.4"),
    ],
)
def test_automatic_release_tag(tags: list[str], expected: str) -> None:
    assert select_release_tag("", tags) == expected


def test_manual_release_tag_overrides_auto_version() -> None:
    assert select_release_tag("v2", ["v1.3"]) == "v2"


def test_invalid_manual_release_tag() -> None:
    with pytest.raises(ValueError, match="release_tag must be a version tag"):
        select_release_tag("release 2", ["v1.3"])
