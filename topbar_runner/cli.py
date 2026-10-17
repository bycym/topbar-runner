"""Command-line entry points for local development and engine smoke runs."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

from topbar_runner.app_config import default_config_path
from topbar_runner.filenames import discover_plugins
from topbar_runner.logging import configure_file_logging, get_logger
from topbar_runner.parser import MenuItem
from topbar_runner.runner import PluginRunner, RunResult, runtime_from_plugin


def main(argv: Sequence[str] | None = None) -> int:
    return run_app_cli(argv)


def dev_main(argv: Sequence[str] | None = None) -> int:
    sample_dir = Path(__file__).resolve().parent.parent / "examples" / "plugins"
    args = _dev_parser(sample_dir).parse_args(argv)
    if args.console:
        return run_cli(
            [
                "--plugin-dir",
                str(args.plugin_dir),
                "--config-path",
                str(args.config_path),
                "--log-path",
                str(args.log_path),
                *(["--debug"] if args.debug else []),
            ]
        )

    from topbar_runner.ui import run_app

    return run_app(args.config_path, args.plugin_dir, args.log_path, args.debug)


def run_cli(argv: Sequence[str] | None = None, default_plugin_dir: Path | None = None) -> int:
    args = _parser(default_plugin_dir).parse_args(argv)
    configure_file_logging(args.log_path, debug=args.debug, stderr=args.debug)
    logger = get_logger()

    plugin_dir = args.plugin_dir
    logger.info(
        "cli starting: plugin_dir=%s config_path=%s log_path=%s debug=%s",
        plugin_dir,
        args.config_path,
        args.log_path,
        args.debug,
    )
    plugins = discover_plugins(plugin_dir)
    if not plugins:
        logger.warning("no plugins found: %s", plugin_dir)
        print(f"No plugins found in {plugin_dir}")
        return 1
    logger.info("discovered %d plugins: %s", len(plugins), ", ".join(p.path.name for p in plugins))

    async def run_once() -> list[RunResult | None]:
        runner = PluginRunner()
        return await asyncio.gather(
            *[
                runner.trigger(runtime_from_plugin(plugin, args.config_path), "dev")
                for plugin in plugins
            ]
        )

    results = asyncio.run(run_once())
    for result in results:
        if result is not None:
            _print_result(result)
    ok = all(result is not None and result.ok for result in results)
    logger.info("cli finished: ok=%s", ok)
    return 0 if ok else 1


def run_app_cli(argv: Sequence[str] | None = None) -> int:
    args = _app_parser().parse_args(argv)
    if args.console:
        return run_cli(
            [
                "--plugin-dir",
                str(args.plugin_dir),
                "--config-path",
                str(args.config_path),
                "--log-path",
                str(args.log_path),
                *(["--debug"] if args.debug else []),
            ]
        )

    from topbar_runner.ui import run_app

    return run_app(args.config_path, args.plugin_dir, args.log_path, args.debug)


def _parser(default_plugin_dir: Path | None) -> argparse.ArgumentParser:
    env_plugin_dir = os.environ.get("TOPBAR_RUNNER_PLUGIN_DIR")
    plugin_dir = Path(env_plugin_dir) if env_plugin_dir else default_plugin_dir

    parser = argparse.ArgumentParser(prog="topbar-runner")
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=plugin_dir,
        required=plugin_dir is None,
        help="Directory containing direct child xbar-style Python plugins.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path(".topbar-runner.toml"),
        help="Config path exposed to plugins through TOPBAR_RUNNER_CONFIG_PATH.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path(".topbar-runner.log"),
        help="Diagnostic log path.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write DEBUG diagnostics and mirror logs to stderr.",
    )
    return parser


def _app_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topbar-runner")
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=None,
        help="Directory containing direct child xbar-style plugins.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=default_config_path(),
        help="Local app config path.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path(".topbar-runner.log"),
        help="Diagnostic log path.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Run one console engine pass instead of launching the PySide6 UI.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write DEBUG diagnostics and mirror logs to stderr.",
    )
    return parser


def _dev_parser(default_plugin_dir: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev")
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=default_plugin_dir,
        help="Directory containing direct child xbar-style Python plugins.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path(".topbar-runner.toml"),
        help="Local app config path.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path(".topbar-runner.log"),
        help="Diagnostic log path.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Run one console engine pass instead of launching the PySide6 UI.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write DEBUG diagnostics and mirror logs to stderr.",
    )
    return parser


def _print_result(result: RunResult) -> None:
    if not result.ok:
        print(f"{result.plugin.path.name}: ERROR {result.error}")
        return
    if result.cached is None or result.cached.render.headline is None:
        print(f"{result.plugin.path.name}: <empty>")
        return

    headline = result.cached.render.headline.text
    extras = ", ".join(item.text for item in result.cached.render.extra_chips)
    menu_count = _count_items(result.cached.render.menu_items)
    suffix = f" | chips: {extras}" if extras else ""
    print(f"{result.plugin.path.name}: {headline} ({menu_count} menu items){suffix}")


def _count_items(items: list[MenuItem]) -> int:
    return sum(1 + _count_items(item.children) for item in items)


if __name__ == "__main__":
    raise SystemExit(main())
