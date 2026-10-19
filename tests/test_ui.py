import os
from pathlib import Path

from topbar_runner.app_config import AppConfig
from topbar_runner.ui import (
    LogsDialog,
    MenuItem,
    QtCore,
    QtWidgets,
    TopbarWindow,
    _bounded_size,
    _chip_label,
    _chip_text,
    _clamped_window_size,
    _disconnect_process,
    _format_bytes,
    _plugin_signature,
    _popup_text,
    _style_sheet,
    _theme_palette,
)


def test_theme_palettes_exist() -> None:
    assert _theme_palette("light")["text"] == "#18181b"
    assert _theme_palette("dark")["text"] == "#f4f4f5"
    assert _theme_palette("synthwave")["border"] == "#ec4899"


def test_style_sheet_uses_theme_values() -> None:
    sheet = _style_sheet("synthwave")

    assert "#ec4899" in sheet
    assert "#dragHandle" in sheet
    assert 'QPushButton[resourceWarning="true"]' in sheet


def test_format_bytes() -> None:
    assert _format_bytes(12) == "12 B"
    assert _format_bytes(2048) == "2.0 KiB"
    assert _format_bytes(3 * 1024 * 1024) == "3.0 MiB"


def test_chip_text_truncates_long_labels() -> None:
    assert _chip_text("short") == "short"
    assert _chip_text("abcdefghijklmnopqrstuvwxyz", 10) == "abcdefg..."


def test_chip_label_uses_plugin_name_for_image_only_items() -> None:
    text, label = _chip_label("met-radar", MenuItem("", attrs={"image": "abc"}))

    assert text == ""
    assert label == "met-radar"


def test_popup_text_uses_fallback_for_image_only_items() -> None:
    assert _popup_text(MenuItem("", attrs={"image": "abc"})) == "Image"


def test_clamped_window_size_fits_content_with_screen_cap() -> None:
    assert _clamped_window_size(480, 44, 1200) == (480, 44)
    assert _clamped_window_size(1600, 30, 1200) == (1200, 36)


def test_bounded_size_scales_large_images() -> None:
    assert _bounded_size(1440, 960, 720, 480) == (720, 480)
    assert _bounded_size(100, 80, 720, 480) == (100, 80)


def test_plugin_signature_changes_when_plugin_file_changes(tmp_path: Path) -> None:
    from topbar_runner.filenames import parse_plugin_filename

    path = tmp_path / "hello.5s.py"
    path.write_text("print('one')", encoding="utf-8")
    plugin = parse_plugin_filename(path)
    assert plugin is not None
    first = _plugin_signature([plugin])

    stat = path.stat()
    path.write_text("print('two')", encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert _plugin_signature([plugin]) != first


def test_disconnect_process_accepts_unconnected_process() -> None:
    process = QtCore.QProcess()

    _disconnect_process(process)


def test_three_dot_menu_can_quit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = TopbarWindow(tmp_path / "config.toml", AppConfig(plugin_dir=tmp_path))
    window.show()
    chip = window.findChild(QtWidgets.QPushButton, "settingsChip")
    assert chip is not None
    menu = chip.menu()
    assert menu is not None
    assert [action.text() for action in menu.actions()] == ["Settings", "View Logs", "Quit"]

    timed_out = []
    guard = QtCore.QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(lambda: timed_out.append(True))
    guard.timeout.connect(app.quit)
    guard.start(2000)
    QtCore.QTimer.singleShot(0, menu.actions()[2].trigger)
    app.exec()
    guard.stop()

    assert not timed_out
    window.close()


def test_view_logs_shows_only_current_run_and_refreshes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    log_path = tmp_path / "custom.log"
    log_path.write_bytes(b"old run\r\n")
    log_start = log_path.stat().st_size
    window = TopbarWindow(
        tmp_path / "config.toml", AppConfig(plugin_dir=tmp_path), log_path, log_start
    )
    chip = window.findChild(QtWidgets.QPushButton, "settingsChip")
    assert chip is not None
    menu = chip.menu()
    assert menu is not None

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("plugin run failed: first error\n")
    menu.actions()[1].trigger()
    app.processEvents()
    dialog = window.findChild(LogsDialog)
    assert dialog is not None
    assert dialog.output.toPlainText() == "plugin run failed: first error\n"

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("plugin run failed: second error\n")
    dialog.refresh()
    assert dialog.output.toPlainText().endswith("plugin run failed: second error\n")
    assert "old run" not in dialog.output.toPlainText()
    window.close()
