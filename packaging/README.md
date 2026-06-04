# Packaging

Portable builds use PyInstaller. Keep runtime dependencies in `pyproject.toml`; install PyInstaller only in build environments.

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
