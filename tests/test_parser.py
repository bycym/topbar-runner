from topbar_runner.parser import parse_stdout


def test_parse_xbar_menu_and_attrs() -> None:
    render = parse_stdout(
        "\n".join(
            [
                "Alpha | color=red size=12",
                "---",
                "Open | href=https://example.com",
                "Hidden chip | dropdown=false",
                "Parent",
                "--Child | alternate=true",
            ]
        )
    )

    assert render.headline is not None
    assert render.headline.text == "Alpha"
    assert render.headline.attrs["color"] == "red"
    assert render.extra_chips[0].text == "Hidden chip"
    assert render.menu_items[0].text == "Open"
    assert render.menu_items[1].children[0].text == "Child"
    assert render.menu_items[1].children[0].alternate is True


def test_malformed_attrs_degrade_gracefully() -> None:
    render = parse_stdout('Title\nBroken | href="unterminated')

    assert render.menu_items[0].text == "Broken"
    assert render.menu_items[0].attrs == {}
    assert render.errors
