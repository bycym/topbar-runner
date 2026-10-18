# Manual

## Run

Install dependencies, then launch app:

```bash
poetry install
poetry run topbar-runner
```

For local development UI:

```bash
poetry run dev
```

For one console smoke run:

```bash
poetry run topbar-runner --console --plugin-dir examples/plugins
```

For debug diagnostics:

```bash
poetry run topbar-runner --console --debug --plugin-dir examples/plugins
```

Debug mode works in console and UI mode. It writes DEBUG logs to `--log-path` and mirrors logs to stderr.

## Plugin Directory

On first launch, choose a plugin directory. Only direct child files in that directory are run. Nested folders are ignored.

Supported plugin files:

- `*.py`
- `*.pyw`
- `*.sh`

Filename intervals follow xbar-style suffixes:

- `hello.5s.py`: run every 5 seconds.
- `weather.15m.py`: run every 15 minutes.
- `status.1h.py`: run every hour.
- `daily.1d.py`: run every day.

Files without interval suffix default to 60 seconds.

## Plugin Output

Plugins print xbar/BitBar-style text:

```text
Headline | color=#22c55e
---
Open Site | href=https://example.com
Copy Token | copy=abc123
Refresh | refresh=true
More
--Nested Item
Hidden Chip | dropdown=false
Alternate Row | alternate=true
```

Top line becomes main chip. Lines after `---` become popup rows. Top-level `dropdown=false` rows become extra chips on topbar.
Image-only headline rows are shown as small icon chips. Image-only popup rows are shown as bounded large image buttons. If the image cannot be decoded, fallback text is shown instead.
Nested `--` menu rows open as hover submenus. Moving out closes the hovered submenu after a short delay, so you can move into the submenu or on to the next row.
Refresh rows rerun the plugin script and close the whole popup stack.

## Actions

Supported v1 actions:

- `href=http://...`, `href=https://...`, `href=mailto:...`: open link.
- `copy=value`: copy text to clipboard.
- `refresh=true`: rerun plugin.

Command execution actions are not supported in v1.

## Runtime

Each plugin run receives:

- `TOPBAR_RUNNER_REASON`: `startup`, `interval`, `manual`, `filesystem`, `settings`, or `coalesced`.
- `TOPBAR_RUNNER_PLUGIN_PATH`: full plugin file path.
- `TOPBAR_RUNNER_PLUGIN_DIR`: plugin directory.
- `TOPBAR_RUNNER_CONFIG_PATH`: app config path.
- `TOPBAR_RUNNER_HOST_OS`: Python platform string.

Plugin process working directory is the plugin directory.

Same plugin does not run twice at once. If a refresh happens while it is still running, one pending rerun is queued.
Filesystem reloads are debounced and ignored unless the direct plugin files or their modification times changed. Plugin cache writes should not cause rerun loops.

## Keybindings

- Hold `Alt` / `Option` while popup is open: show `alternate=true` rows.
- Drag handle `::::`: move topbar window.

## Settings

Open `Settings` chip to change:

- Plugin directory.
- Theme.
- Keep on top.
- Launch at login flag.

Window position and size are saved automatically when moved or resized.
When plugins load or refresh, the bar expands to fit visible chips and clamps to the available screen width.

Advanced config keys:

```toml
plugin_order = ["weather.15m.py", "clock.5s.py"]
disabled_plugins = ["slow.1m.py"]
```

Names are plugin filenames. Ordered plugins appear first; unlisted enabled plugins keep lexical filename order after them.
External config edits are watched and applied after a short debounce.

Default config path:

- macOS: `~/Library/Application Support/topbar-runner/config.toml`
- Linux: `$XDG_CONFIG_HOME/topbar-runner/config.toml` or `~/.config/topbar-runner/config.toml`
- Windows: `%APPDATA%\topbar-runner\config.toml`

Launch at login creates or removes a user-level startup file for the current platform. It does not require admin privileges.

## Diagnostics

The UI writes logs next to the app config path, using the same filename with `.log`. Finder launches work even when its working directory is not writable. Pass `--log-path` to choose another location.
Console mode writes logs to `.topbar-runner.log` unless `--log-path` is passed.

## Packaging

Portable build instructions live in `packaging/README.md`. The PyInstaller spec is `packaging/pyinstaller/topbar-runner.spec`.

Run `Build and release` manually from GitHub Actions. Every run tests, builds, and smoke tests Apple Silicon and Intel macOS, Ubuntu, and Windows apps, then keeps their archives as workflow artifacts. On macOS, choose the `apple-silicon` archive for Apple Silicon or `intel` for Intel. To publish them, select `Publish a GitHub Release` and enter a version tag such as `v0.1.0`. An existing tag must point to the selected build commit; if the tag does not exist, publication creates it at that commit. Python plugins in portable builds use `python3` or `python` from the user's `PATH`, so install Python separately to run them. Shell plugins on macOS and Linux use `bash`.
