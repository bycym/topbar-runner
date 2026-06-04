from topbar_runner.actions import is_allowed_href


def test_href_allowlist() -> None:
    assert is_allowed_href("https://example.com")
    assert is_allowed_href("http://example.com")
    assert is_allowed_href("mailto:test@example.com")
    assert not is_allowed_href("file:///etc/passwd")
    assert not is_allowed_href("javascript:alert(1)")
