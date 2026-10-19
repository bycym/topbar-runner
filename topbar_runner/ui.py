"""PySide6 desktop host for the floating topbar UI."""

from __future__ import annotations

import base64
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil

from topbar_runner.actions import is_allowed_href
from topbar_runner.app_config import AppConfig, WindowState, load_config, save_config
from topbar_runner.cache import RenderCache
from topbar_runner.filenames import PluginFile, apply_plugin_preferences, discover_plugins
from topbar_runner.launch_at_login import launch_command, set_launch_at_login
from topbar_runner.logging import configure_file_logging, get_logger
from topbar_runner.parser import MenuItem, PluginRender
from topbar_runner.runner import runtime_from_plugin

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when dep absent
    raise SystemExit("PySide6 is required. Run `poetry install` first.") from exc


class QtPluginRunner(QtCore.QObject):
    render_updated = QtCore.Signal(object, object)
    resource_warning = QtCore.Signal(object, object)

    CPU_WARNING_PERCENT = 80.0
    MEMORY_WARNING_BYTES = 256 * 1024 * 1024
    RESOURCE_SAMPLE_MS = 1000

    def __init__(self, config_path: Path, cache: RenderCache) -> None:
        super().__init__()
        self.config_path = config_path
        self.cache = cache
        self._processes: dict[Path, QtCore.QProcess] = {}
        self._resource_processes: dict[Path, psutil.Process] = {}
        self._resource_logged: set[Path] = set()
        self._cancelled: set[Path] = set()
        self._pending: set[Path] = set()
        self._timeouts: dict[Path, QtCore.QTimer] = {}
        self._resource_timers: dict[Path, QtCore.QTimer] = {}

    def trigger(self, plugin: PluginFile, reason: str = "manual") -> None:
        if plugin.path in self._processes:
            get_logger().debug("qt plugin run coalesced: %s reason=%s", plugin.path, reason)
            self._pending.add(plugin.path)
            return

        runtime = runtime_from_plugin(plugin, self.config_path)
        self._cancelled.discard(plugin.path)
        plugin_path = plugin.path.resolve()
        plugin_dir = plugin.path.parent.resolve()
        process = QtCore.QProcess(self)
        process.setProgram(runtime.interpreter)
        process.setArguments([str(plugin_path)])
        process.setWorkingDirectory(str(plugin_dir))
        env = QtCore.QProcessEnvironment.systemEnvironment()
        for key, value in {
            **runtime.extra_env,
            "TOPBAR_RUNNER_REASON": reason,
            "TOPBAR_RUNNER_PLUGIN_PATH": str(plugin_path),
            "TOPBAR_RUNNER_PLUGIN_DIR": str(plugin_dir),
            "TOPBAR_RUNNER_CONFIG_PATH": str(self.config_path),
            "TOPBAR_RUNNER_HOST_OS": sys.platform,
        }.items():
            env.insert(key, value)
        process.setProcessEnvironment(env)

        timeout = QtCore.QTimer(self)
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: self._timeout(plugin, runtime.timeout_seconds))
        process.finished.connect(
            lambda code, _status, process=process: self._finished(plugin, process, code)
        )
        process.errorOccurred.connect(
            lambda _error, process=process: self._failed(plugin, process, process.errorString())
        )
        process.started.connect(lambda: self._start_resource_tracking(plugin, process))

        self._processes[plugin.path] = process
        self._timeouts[plugin.path] = timeout
        timeout.start(int(runtime.timeout_seconds * 1000))
        get_logger().debug(
            "qt plugin run starting: path=%s interpreter=%s cwd=%s reason=%s timeout=%ss",
            plugin_path,
            runtime.interpreter,
            plugin_dir,
            reason,
            runtime.timeout_seconds,
        )
        process.start()

    def cancel_all(self) -> None:
        self._cancelled.update(self._processes)
        for process in list(self._processes.values()):
            _disconnect_process(process)
            process.kill()
            process.waitForFinished(250)
            process.deleteLater()
        for timeout in self._timeouts.values():
            timeout.stop()
        for timer in self._resource_timers.values():
            timer.stop()
        self._processes.clear()
        self._resource_processes.clear()
        self._resource_logged.clear()
        self._cancelled.clear()
        self._timeouts.clear()
        self._resource_timers.clear()
        self._pending.clear()

    def _start_resource_tracking(self, plugin: PluginFile, process: QtCore.QProcess) -> None:
        pid = process.processId()
        if pid <= 0:
            return
        try:
            tracked = psutil.Process(pid)
            tracked.cpu_percent(None)
        except psutil.Error:
            return

        timer = QtCore.QTimer(self)
        timer.timeout.connect(lambda: self._sample_resources(plugin))
        timer.start(self.RESOURCE_SAMPLE_MS)
        self._resource_processes[plugin.path] = tracked
        self._resource_timers[plugin.path] = timer

    def _sample_resources(self, plugin: PluginFile) -> None:
        if plugin.path not in self._processes:
            return
        process = self._resource_processes.get(plugin.path)
        if process is None:
            return
        try:
            cpu_percent = process.cpu_percent(None)
            rss_bytes = process.memory_info().rss
        except psutil.Error:
            return

        if cpu_percent >= self.CPU_WARNING_PERCENT or rss_bytes >= self.MEMORY_WARNING_BYTES:
            details = PluginResourceWarning(
                cpu_percent=cpu_percent,
                rss_bytes=rss_bytes,
                cpu_limit=self.CPU_WARNING_PERCENT,
                rss_limit=self.MEMORY_WARNING_BYTES,
            )
            if plugin.path not in self._resource_logged:
                self._resource_logged.add(plugin.path)
                get_logger().warning(
                    "plugin resource warning: %s cpu=%.1f%% rss=%d bytes",
                    plugin.path,
                    cpu_percent,
                    rss_bytes,
                )
            self._emit_resource_warning(plugin, details)

    def _timeout(self, plugin: PluginFile, timeout_seconds: float) -> None:
        process = self._processes.get(plugin.path)
        if process is not None:
            process.kill()
        self._fail_active(plugin, f"timeout after {timeout_seconds:g}s")

    def _finished(self, plugin: PluginFile, process: QtCore.QProcess, code: int) -> None:
        if self._processes.get(plugin.path) is not process or plugin.path in self._cancelled:
            return
        if code != 0:
            error = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
            self._fail_active(plugin, f"exit {code}: {error}")
            return

        from topbar_runner.parser import parse_stdout

        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._cleanup_process(plugin)
        render = parse_stdout(output)
        cached = self.cache.set_good(str(plugin.path), render)
        get_logger().info(
            "qt plugin run succeeded: %s stdout_chars=%d menu_items=%d headline=%r",
            plugin.path,
            len(output),
            len(render.menu_items),
            render.headline.text if render.headline is not None else None,
        )
        self._emit_render(plugin, cached)
        self._run_pending(plugin)

    def _failed(self, plugin: PluginFile, process: QtCore.QProcess, error: str) -> None:
        if self._processes.get(plugin.path) is not process or plugin.path in self._cancelled:
            return
        self._fail_active(plugin, error)

    def _fail_active(self, plugin: PluginFile, error: str) -> None:
        if plugin.path not in self._processes:
            return
        self._cleanup_process(plugin)
        get_logger().warning("plugin run failed: %s: %s", plugin.path, error)
        cached = self.cache.mark_failed(str(plugin.path), error)
        self._emit_render(plugin, cached)
        self._run_pending(plugin)

    def _cleanup_process(self, plugin: PluginFile) -> None:
        process = self._processes.pop(plugin.path, None)
        if process is not None:
            _disconnect_process(process)
            if process.state() != QtCore.QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(250)
            process.deleteLater()
        timeout = self._timeouts.pop(plugin.path, None)
        self._stop_resource_tracking(plugin)
        if timeout is not None:
            timeout.stop()

    def _emit_render(self, plugin: PluginFile, cached: object) -> None:
        try:
            self.render_updated.emit(plugin, cached)
        except RuntimeError:
            get_logger().debug("skip render signal for deleted receiver: %s", plugin.path)

    def _emit_resource_warning(self, plugin: PluginFile, warning: PluginResourceWarning) -> None:
        try:
            self.resource_warning.emit(plugin, warning)
        except RuntimeError:
            get_logger().debug("skip resource signal for deleted receiver: %s", plugin.path)

    def _stop_resource_tracking(self, plugin: PluginFile) -> None:
        timer = self._resource_timers.pop(plugin.path, None)
        if timer is not None:
            timer.stop()
        self._resource_processes.pop(plugin.path, None)
        self._resource_logged.discard(plugin.path)

    def _run_pending(self, plugin: PluginFile) -> None:
        if plugin.path in self._pending:
            self._pending.remove(plugin.path)
            self.trigger(plugin, "coalesced")


@dataclass(frozen=True, slots=True)
class PluginResourceWarning:
    cpu_percent: float
    rss_bytes: int
    cpu_limit: float
    rss_limit: int


def _disconnect_process(process: QtCore.QProcess) -> None:
    for signal in (process.finished, process.errorOccurred, process.started):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass


class TopbarWindow(QtWidgets.QWidget):
    FILESYSTEM_RELOAD_DEBOUNCE_MS = 750

    def __init__(
        self,
        config_path: Path,
        config: AppConfig,
        log_path: Path | None = None,
        log_start: int = 0,
    ) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = config
        self.log_path = log_path or config_path.with_suffix(".log")
        self.log_start = log_start
        self._logs_dialog: LogsDialog | None = None
        self.cache = RenderCache()
        self.runner = QtPluginRunner(config_path, self.cache)
        self.runner.render_updated.connect(self._render_updated)
        self.runner.resource_warning.connect(self._resource_warning)
        self.plugins: list[PluginFile] = []
        self._renders: dict[Path, PluginRender] = {}
        self._resource_warnings: dict[Path, PluginResourceWarning] = {}
        self._timers: dict[Path, QtCore.QTimer] = {}
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _path: self._schedule_filesystem_reload())
        self._watcher.fileChanged.connect(lambda _path: self._schedule_filesystem_reload())
        self._filesystem_reload_timer = QtCore.QTimer(self)
        self._filesystem_reload_timer.setSingleShot(True)
        self._filesystem_reload_timer.timeout.connect(self._reload_plugins_if_changed)
        self._plugin_signature: tuple[tuple[str, int], ...] = ()
        self._config_signature: tuple[str, int] = _path_signature(self.config_path)
        self._drag_origin: QtCore.QPoint | None = None
        self._popup: PopupPanel | None = None

        self.setWindowTitle("topbar-runner")
        self._apply_window_flags()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(6)
        self.setStyleSheet(_style_sheet(self.config.theme))
        self.setGeometry(
            config.window.x,
            config.window.y,
            config.window.width,
            config.window.height,
        )
        self._ensure_plugin_dir()
        self._reload_plugins("startup")

    def _ensure_plugin_dir(self) -> None:
        if self.config.plugin_dir is None:
            selected = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose plugin directory")
            if selected:
                self.config.plugin_dir = Path(selected)
                self._save_config()
            else:
                self.config.plugin_dir = (
                    Path(__file__).resolve().parent.parent / "examples" / "plugins"
                )

    def _reload_plugins(self, reason: str) -> None:
        self.runner.cancel_all()
        for timer in self._timers.values():
            timer.stop()
        self._timers.clear()

        plugin_dir = self.config.plugin_dir
        self.plugins = (
            _configured_plugins(discover_plugins(plugin_dir), self.config) if plugin_dir else []
        )
        self._plugin_signature = _plugin_signature(self.plugins)
        self._config_signature = _path_signature(self.config_path)
        get_logger().info(
            "reload plugins: reason=%s plugin_dir=%s count=%d plugins=%s",
            reason,
            plugin_dir,
            len(self.plugins),
            ", ".join(plugin.path.name for plugin in self.plugins),
        )
        current_paths = {plugin.path for plugin in self.plugins}
        self._renders = {
            path: render for path, render in self._renders.items() if path in current_paths
        }
        self._resource_warnings = {
            path: warning
            for path, warning in self._resource_warnings.items()
            if path in current_paths
        }
        self._watch_plugin_paths(current_paths)
        self._refresh_bar()
        for plugin in self.plugins:
            self.runner.trigger(plugin, reason)
            timer = QtCore.QTimer(self)
            timer.timeout.connect(lambda plugin=plugin: self.runner.trigger(plugin, "interval"))
            timer.start(plugin.interval_seconds * 1000)
            self._timers[plugin.path] = timer

    def _schedule_filesystem_reload(self) -> None:
        get_logger().debug(
            "filesystem change detected; scheduling reload in %dms",
            self.FILESYSTEM_RELOAD_DEBOUNCE_MS,
        )
        self._filesystem_reload_timer.start(self.FILESYSTEM_RELOAD_DEBOUNCE_MS)

    def _reload_plugins_if_changed(self) -> None:
        config_changed = _path_signature(self.config_path) != self._config_signature
        reason = "filesystem"
        if config_changed:
            old_config = self.config
            self.config = load_config(self.config_path)
            self._config_signature = _path_signature(self.config_path)
            self._apply_config_changes(old_config)
            reason = "config"

        plugin_dir = self.config.plugin_dir
        plugins = (
            _configured_plugins(discover_plugins(plugin_dir), self.config) if plugin_dir else []
        )
        signature = _plugin_signature(plugins)
        if signature == self._plugin_signature:
            if config_changed:
                self._refresh_bar()
                self._watch_plugin_paths({plugin.path for plugin in self.plugins})
                return
            get_logger().debug("filesystem reload skipped; plugin files unchanged")
            return
        self._reload_plugins(reason)

    def _watch_plugin_paths(self, plugin_paths: set[Path]) -> None:
        watched = self._watcher.files() + self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        directories: list[str] = []
        if self.config.plugin_dir is not None and self.config.plugin_dir.exists():
            directories.append(str(self.config.plugin_dir))
        if self.config_path.parent.exists():
            directories.append(str(self.config_path.parent))
        if directories:
            self._watcher.addPaths(sorted(set(directories)))
        existing_files = [str(path) for path in plugin_paths if path.exists()]
        if self.config_path.exists():
            existing_files.append(str(self.config_path))
        if existing_files:
            self._watcher.addPaths(sorted(set(existing_files)))

    def _render_updated(self, plugin: PluginFile, cached: object) -> None:
        if cached is not None and getattr(cached, "render", None) is not None:
            self._renders[plugin.path] = cached.render
        self._refresh_bar()

    def _resource_warning(self, plugin: PluginFile, warning: object) -> None:
        if isinstance(warning, PluginResourceWarning):
            self._resource_warnings[plugin.path] = warning
        self._refresh_bar()

    def _refresh_bar(self) -> None:
        _clear_layout(self._layout)
        self._layout.addWidget(DragHandle(self))
        for plugin in self.plugins:
            render = self._renders.get(plugin.path)
            if render is None or render.headline is None:
                self._add_chip(plugin, MenuItem(plugin.name), stale=True)
                continue
            self._add_chip(plugin, render.headline)
            for item in render.extra_chips:
                self._add_chip(plugin, item)
        settings = QtWidgets.QPushButton("...")
        settings.setObjectName("settingsChip")
        settings.setToolTip("Settings, View Logs, and Quit")
        settings.setFixedWidth(32)
        menu = QtWidgets.QMenu(settings)
        menu.addAction("Settings", self._open_settings)
        menu.addAction("View Logs", self._open_logs)
        menu.addAction("Quit", QtWidgets.QApplication.quit)
        settings.setMenu(menu)
        self._layout.addWidget(settings)
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        self._layout.activate()
        size = self.sizeHint()
        screen = self.screen() or QtWidgets.QApplication.primaryScreen()
        available_width = screen.availableGeometry().width() if screen is not None else size.width()
        width, height = _clamped_window_size(size.width(), size.height(), available_width)
        if self.width() != width or self.height() != height:
            self.resize(width, height)

    def _add_chip(self, plugin: PluginFile, item: MenuItem, stale: bool = False) -> None:
        text, label = _chip_label(plugin.name, item)
        button = QtWidgets.QPushButton(_chip_text(label))
        button.setProperty("stale", stale)
        button.setMaximumWidth(180)
        button.setToolTip(f"{plugin.path.name}\n{label}")
        warning = self._resource_warnings.get(plugin.path)
        button.setProperty("resourceWarning", warning is not None)
        if warning is not None:
            button.setToolTip(
                f"{plugin.path.name}\n{label}\nHigh resource use: CPU {warning.cpu_percent:.1f}% / "
                f"RSS {_format_bytes(warning.rss_bytes)}"
            )
        _apply_text_attrs(button, item, self.config.theme)
        if not text and button.icon().isNull():
            button.setText(_chip_text(plugin.name))
        elif not text:
            button.setText("")
            button.setFixedWidth(36)
        button.clicked.connect(lambda: self._open_popup(plugin, button))
        self._layout.addWidget(button)

    def _open_popup(self, plugin: PluginFile, anchor: QtWidgets.QWidget) -> None:
        render = self._renders.get(plugin.path)
        if render is None:
            return
        if self._popup is not None:
            self._popup.close()
        self._popup = PopupPanel(
            render,
            lambda: self.runner.trigger(plugin, "manual"),
            self.config.theme,
        )
        pos = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height() + 4))
        self._popup.move(pos)
        self._popup.show()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            old_plugin_dir = self.config.plugin_dir
            self.config = dialog.config
            self._save_config()
            self._apply_launch_at_login()
            self.setStyleSheet(_style_sheet(self.config.theme))
            self._apply_window_flags()
            if self.config.plugin_dir != old_plugin_dir:
                self._reload_plugins("settings")
            self.show()

    def _open_logs(self) -> None:
        if self._logs_dialog is None:
            self._logs_dialog = LogsDialog(self.log_path, self.log_start, self)
        self._logs_dialog.show()
        self._logs_dialog.raise_()
        self._logs_dialog.activateWindow()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_origin = None
        self._save_window()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._save_window()
        super().resizeEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.runner.cancel_all()
        super().closeEvent(event)

    def _save_window(self) -> None:
        geometry = self.geometry()
        self.config.window = WindowState(
            x=geometry.x(),
            y=geometry.y(),
            width=geometry.width(),
            height=geometry.height(),
        )
        self._save_config()

    def _apply_window_flags(self) -> None:
        flags = QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Tool
        if self.config.keep_on_top:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _apply_config_changes(self, old_config: AppConfig) -> None:
        if self.config.theme != old_config.theme:
            self.setStyleSheet(_style_sheet(self.config.theme))
        if self.config.keep_on_top != old_config.keep_on_top:
            self._apply_window_flags()
            self.show()
        if self.config.launch_at_login != old_config.launch_at_login:
            self._apply_launch_at_login()
        if self.config.window != old_config.window:
            self.setGeometry(
                self.config.window.x,
                self.config.window.y,
                self.config.window.width,
                self.config.window.height,
            )

    def _save_config(self) -> None:
        save_config(self.config_path, self.config)
        self._config_signature = _path_signature(self.config_path)

    def _apply_launch_at_login(self) -> None:
        try:
            set_launch_at_login(
                self.config.launch_at_login,
                launch_command(self.config_path),
            )
        except OSError as exc:
            get_logger().warning("failed to update launch-at-login: %s", exc)


class DragHandle(QtWidgets.QLabel):
    def __init__(self, window: TopbarWindow) -> None:
        super().__init__("|")
        self.window = window
        self.setObjectName("dragHandle")
        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Move")
        self.setFixedSize(10, 24)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._drag_origin: QtCore.QPoint | None = None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_origin = (
                event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self._drag_origin)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_origin = None
        self.window._save_window()
        super().mouseReleaseEvent(event)


class PopupPanel(QtWidgets.QFrame):
    def __init__(
        self,
        render: PluginRender,
        refresh: Callable[[], None],
        theme: str,
        items: list[MenuItem] | None = None,
        parent_panel: PopupPanel | None = None,
    ) -> None:
        super().__init__(None, QtCore.Qt.WindowType.Popup)
        self.render = render
        self.refresh = refresh
        self.items = items if items is not None else render.menu_items
        self.theme = theme
        self.parent_panel = parent_panel
        self._submenu: PopupPanel | None = None
        self._submenu_close_timer = QtCore.QTimer(self)
        self._submenu_close_timer.setSingleShot(True)
        self._submenu_close_timer.timeout.connect(self._close_submenu_if_unhovered)
        self.setObjectName("popupPanel")
        self.setStyleSheet(_style_sheet(theme))
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)
        self._alt = False
        self._build()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Alt:
            self._alt = True
            self._build()

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Alt:
            self._alt = False
            self._build()

    def _build(self) -> None:
        _clear_layout(self._layout)
        if self._submenu is not None:
            self._submenu.close()
            self._submenu = None
        for item in self.items:
            self._add_item(item)

    def _add_item(self, item: MenuItem) -> None:
        if item.alternate != self._alt and item.alternate:
            return
        row = PopupButton(item, self)
        _configure_popup_button(row, item, self.theme)
        row.setObjectName("popupItem")
        row.clicked.connect(lambda: self._activate(item))
        self._layout.addWidget(row)

    def _show_submenu(self, item: MenuItem, anchor: QtWidgets.QWidget) -> None:
        self._cancel_submenu_close()
        if not item.children:
            self._close_submenu()
            return
        if self._submenu is not None:
            self._submenu.close()
        self._submenu = PopupPanel(
            self.render,
            self.refresh,
            self.theme,
            item.children,
            parent_panel=self,
        )
        pos = anchor.mapToGlobal(QtCore.QPoint(anchor.width() + 4, 0))
        self._submenu.move(pos)
        self._submenu.show()

    def _schedule_submenu_close(self) -> None:
        self._submenu_close_timer.start(180)

    def _cancel_submenu_close(self) -> None:
        self._submenu_close_timer.stop()

    def _close_submenu(self) -> None:
        if self._submenu is not None:
            self._submenu.close()
            self._submenu = None

    def _close_submenu_if_unhovered(self) -> None:
        if self._submenu is None:
            return
        cursor = QtGui.QCursor.pos()
        if _contains_global_point(self, cursor) or _contains_global_point(self._submenu, cursor):
            return
        self._close_submenu()

    def _root_panel(self) -> PopupPanel:
        panel = self
        while panel.parent_panel is not None:
            panel = panel.parent_panel
        return panel

    def enterEvent(self, event: QtCore.QEvent) -> None:
        if self.parent_panel is not None:
            self.parent_panel._cancel_submenu_close()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self.parent_panel is not None:
            self.parent_panel._schedule_submenu_close()
        super().leaveEvent(event)

    def _activate(self, item: MenuItem) -> None:
        href = item.attrs.get("href")
        copy_text = item.attrs.get("copy")
        if isinstance(href, str) and is_allowed_href(href):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(href))
            self.close()
            return
        if isinstance(copy_text, str):
            QtWidgets.QApplication.clipboard().setText(copy_text)
            self.close()
            return
        if item.attrs.get("refresh") is True or item.attrs.get("refresh") == "true":
            self.refresh()
            self._root_panel().close()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._submenu_close_timer.stop()
        self._close_submenu()
        super().closeEvent(event)


class PopupButton(QtWidgets.QPushButton):
    def __init__(self, item: MenuItem, panel: PopupPanel) -> None:
        super().__init__()
        self.item = item
        self.panel = panel

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self.panel._cancel_submenu_close()
        self.panel._show_submenu(self.item, self)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self.item.children:
            self.panel._schedule_submenu_close()
        super().leaveEvent(event)


class LogsDialog(QtWidgets.QDialog):
    def __init__(self, log_path: Path, log_start: int, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.log_path = log_path
        self.log_start = log_start
        self.setWindowTitle("Current Run Logs")
        self.resize(800, 500)

        layout = QtWidgets.QVBoxLayout(self)
        self.output = QtWidgets.QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setFont(
            QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        )
        layout.addWidget(self.output)
        layout.addWidget(QtWidgets.QLabel(str(log_path)))

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)

    def refresh(self) -> None:
        try:
            with self.log_path.open("rb") as log_file:
                size = log_file.seek(0, 2)
                log_file.seek(self.log_start if size >= self.log_start else 0)
                content = log_file.read().decode("utf-8", errors="replace")
        except OSError as exc:
            content = f"Could not read log {self.log_path}: {exc}"
        if content != self.output.toPlainText():
            scrollbar = self.output.verticalScrollBar()
            position = scrollbar.value()
            at_end = position == scrollbar.maximum()
            self.output.setPlainText(content)
            scrollbar.setValue(scrollbar.maximum() if at_end else position)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        self.refresh()
        self._refresh_timer.start(1000)
        super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._refresh_timer.stop()
        super().hideEvent(event)


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config: AppConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = AppConfig(
            plugin_dir=config.plugin_dir,
            theme=config.theme,
            keep_on_top=config.keep_on_top,
            launch_at_login=config.launch_at_login,
            plugin_order=list(config.plugin_order),
            disabled_plugins=set(config.disabled_plugins),
            window=config.window,
        )
        self.setWindowTitle("Settings")
        layout = QtWidgets.QFormLayout(self)
        self.plugin_dir = QtWidgets.QLineEdit(
            str(config.plugin_dir) if config.plugin_dir is not None else ""
        )
        browse = QtWidgets.QPushButton("Browse")
        browse.clicked.connect(self._browse)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.plugin_dir)
        row.addWidget(browse)
        layout.addRow("Plugin directory", row)
        self.theme = QtWidgets.QComboBox()
        self.theme.addItems(["light", "dark", "synthwave"])
        self.theme.setCurrentText(config.theme)
        layout.addRow("Theme", self.theme)
        self.keep_on_top = QtWidgets.QCheckBox()
        self.keep_on_top.setChecked(config.keep_on_top)
        layout.addRow("Keep on top", self.keep_on_top)
        self.launch = QtWidgets.QCheckBox()
        self.launch.setChecked(config.launch_at_login)
        layout.addRow("Launch at login", self.launch)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        value = self.plugin_dir.text().strip()
        self.config.plugin_dir = Path(value).expanduser() if value else None
        self.config.theme = self.theme.currentText()
        self.config.keep_on_top = self.keep_on_top.isChecked()
        self.config.launch_at_login = self.launch.isChecked()
        super().accept()

    def _browse(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose plugin directory")
        if selected:
            self.plugin_dir.setText(selected)


def run_app(
    config_path: Path,
    plugin_dir: Path | None = None,
    log_path: Path | None = None,
    debug: bool = False,
) -> int:
    config = load_config(config_path)
    if plugin_dir is not None:
        config.plugin_dir = plugin_dir
    log_path = log_path or config_path.with_suffix(".log")
    log_start = log_path.stat().st_size if log_path.exists() else 0
    configure_file_logging(log_path, debug=debug, stderr=debug)
    get_logger().info(
        "ui starting: config_path=%s log_path=%s plugin_dir=%s debug=%s",
        config_path,
        log_path,
        config.plugin_dir,
        debug,
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = TopbarWindow(config_path, config, log_path, log_start)
    window.show()
    return int(app.exec())


def _display_text(item: MenuItem) -> str:
    text = item.text
    length = item.attrs.get("length")
    if isinstance(length, str) and length.isdigit():
        text = text[: int(length)]
    return text


def _popup_text(item: MenuItem) -> str:
    text = _display_text(item)
    if text:
        return text
    if _item_image_attr(item) is not None:
        return "Image"
    return ""


def _chip_text(text: str, max_chars: int = 24) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3]}..."


def _chip_label(plugin_name: str, item: MenuItem) -> tuple[str, str]:
    text = _display_text(item)
    if text:
        return text, text
    if _item_image_attr(item) is not None:
        return "", plugin_name
    return text, plugin_name


def _apply_text_attrs(widget: QtWidgets.QWidget, item: MenuItem, theme: str) -> None:
    style: list[str] = []
    color = item.attrs.get("color")
    size = item.attrs.get("size")
    font = item.attrs.get("font")
    if isinstance(color, str):
        style.append(f"color: {color};")
    if isinstance(size, str) and size.isdigit():
        style.append(f"font-size: {size}px;")
    if isinstance(font, str):
        style.append(f"font-family: {font};")
    if style:
        widget.setStyleSheet("".join(style))
    if isinstance(widget, QtWidgets.QPushButton):
        pixmap = _pixmap_for_item(item, theme)
        if pixmap is not None:
            widget.setIcon(QtGui.QIcon(pixmap))
            widget.setIconSize(QtCore.QSize(18, 18))


def _configure_popup_button(button: QtWidgets.QPushButton, item: MenuItem, theme: str) -> None:
    text = _popup_text(item)
    pixmap = _pixmap_for_item(item, theme)
    if pixmap is not None and not _display_text(item):
        size = _bounded_size(pixmap.width(), pixmap.height(), 720, 480)
        button.setText("")
        button.setIcon(QtGui.QIcon(pixmap))
        button.setIconSize(QtCore.QSize(*size))
        button.setFixedSize(size[0] + 18, size[1] + 18)
        button.setToolTip("Radar image")
        return

    suffix = "  >" if item.children else ""
    button.setText(f"{text}{suffix}")
    _apply_text_attrs(button, item, theme)


def _bounded_size(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return 0, 0
    scale = min(max_width / width, max_height / height, 1)
    return max(1, int(width * scale)), max(1, int(height * scale))


def _item_image_attr(item: MenuItem) -> str | None:
    image = item.attrs.get("image") or item.attrs.get("templateImage")
    return image if isinstance(image, str) else None


def _pixmap_for_item(item: MenuItem, theme: str) -> QtGui.QPixmap | None:
    image = item.attrs.get("image")
    if isinstance(image, str):
        return _pixmap_from_base64(image)

    template_image = item.attrs.get("templateImage")
    if not isinstance(template_image, str):
        return None
    pixmap = _pixmap_from_base64(template_image)
    if pixmap is None:
        return None
    return _tint_pixmap(pixmap, _theme_palette(theme)["text"]) or pixmap


def _pixmap_from_base64(value: str) -> QtGui.QPixmap | None:
    try:
        data = base64.b64decode(value, validate=True)
    except ValueError:
        return None
    pixmap = QtGui.QPixmap()
    if pixmap.loadFromData(data):
        return pixmap
    return None


def _tint_pixmap(pixmap: QtGui.QPixmap, color: str) -> QtGui.QPixmap | None:
    if pixmap.isNull():
        return None
    tinted = QtGui.QPixmap(pixmap.size())
    tinted.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(tinted)
    if not painter.isActive():
        return None
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QtGui.QColor(color))
    painter.end()
    return tinted


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def _clamped_window_size(
    content_width: int,
    content_height: int,
    available_width: int,
) -> tuple[int, int]:
    return max(120, min(content_width, available_width)), max(36, content_height)


def _configured_plugins(plugins: list[PluginFile], config: AppConfig) -> list[PluginFile]:
    return apply_plugin_preferences(plugins, config.plugin_order, config.disabled_plugins)


def _plugin_signature(plugins: list[PluginFile]) -> tuple[tuple[str, int], ...]:
    return tuple(
        (str(plugin.path), plugin.path.stat().st_mtime_ns if plugin.path.exists() else -1)
        for plugin in plugins
    )


def _path_signature(path: Path) -> tuple[str, int]:
    return (str(path), path.stat().st_mtime_ns if path.exists() else -1)


def _contains_global_point(widget: QtWidgets.QWidget, point: QtCore.QPoint) -> bool:
    local = widget.mapFromGlobal(point)
    return widget.rect().contains(local)


def _clear_layout(layout: QtWidgets.QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _style_sheet(theme: str) -> str:
    palette = _theme_palette(theme)
    return f"""
    QWidget {{
      color: {palette["text"]};
      font-size: 13px;
    }}
    TopbarWindow, QWidget {{
      background: transparent;
    }}
    QPushButton {{
      background: {palette["chip"]};
      border: 1px solid {palette["border"]};
      border-radius: 6px;
      padding: 4px 8px;
      min-height: 22px;
    }}
    QPushButton:hover {{
      background: {palette["hover"]};
    }}
    QPushButton[stale="true"] {{
      color: {palette["warning"]};
    }}
    QPushButton[resourceWarning="true"] {{
      border: 2px solid #ef4444;
    }}
    #settingsChip {{
      color: {palette["muted"]};
      padding: 4px 0;
    }}
    QMenu {{
      background: {palette["panel"]};
      border: 1px solid {palette["border"]};
    }}
    QMenu::item {{
      padding: 6px 24px;
    }}
    QMenu::item:selected {{
      background: {palette["hover"]};
    }}
    #dragHandle {{
      color: {palette["muted"]};
      background: transparent;
      border: none;
      padding: 0;
      font-size: 16px;
    }}
    #popupPanel {{
      background: {palette["panel"]};
      border: 1px solid {palette["border"]};
      border-radius: 6px;
    }}
    #popupItem {{
      text-align: left;
      min-width: 220px;
    }}
    """


def _theme_palette(theme: str) -> dict[str, str]:
    palettes = {
        "light": {
            "text": "#18181b",
            "muted": "#71717a",
            "chip": "#fafafa",
            "hover": "#e4e4e7",
            "panel": "#ffffff",
            "border": "#d4d4d8",
            "handle": "#f4f4f5",
            "warning": "#b45309",
        },
        "dark": {
            "text": "#f4f4f5",
            "muted": "#a1a1aa",
            "chip": "#18181b",
            "hover": "#27272a",
            "panel": "#18181b",
            "border": "#3f3f46",
            "handle": "#27272a",
            "warning": "#f59e0b",
        },
        "synthwave": {
            "text": "#fdf4ff",
            "muted": "#f0abfc",
            "chip": "#2e1065",
            "hover": "#4c1d95",
            "panel": "#1e1b4b",
            "border": "#ec4899",
            "handle": "#701a75",
            "warning": "#facc15",
        },
    }
    return palettes.get(theme, palettes["dark"])
