# Packaging

Portable builds use PyInstaller. Keep runtime dependencies in `pyproject.toml`; install PyInstaller only in build environments.

Push a `v*` tag to run the release workflow. It tests all platforms, builds and smoke tests each native app, then publishes macOS and Ubuntu `.tar.gz` archives plus a Windows `.zip` archive to GitHub Releases. The Ubuntu runner installs Qt's required system libraries, including `libegl1`, before tests and packaging.

Portable apps run Python plugins with a separate `python3` or `python` executable found on `PATH`; users need Python installed. A plugin can override its interpreter in metadata. On macOS and Linux, shell plugins use `bash`.

## macOS

```bash
poetry install
poetry run pip install pyinstaller
poetry run pyinstaller packaging/pyinstaller/topbar-runner.spec
```

Output:

- `dist/topbar-runner.app`

## Linux

```bash
poetry install
poetry run pip install pyinstaller
poetry run pyinstaller packaging/pyinstaller/topbar-runner.spec
```

Output:

- `dist/topbar-runner/topbar-runner`

AppImage packaging can wrap that directory with `appimagetool`.

## Windows

```powershell
poetry install
poetry run pip install pyinstaller
poetry run pyinstaller packaging\pyinstaller\topbar-runner.spec
```

Output:

- `dist\topbar-runner\topbar-runner.exe`

## Smoke Test

After building, run:

```bash
dist/topbar-runner/topbar-runner --console --plugin-dir examples/plugins
```
