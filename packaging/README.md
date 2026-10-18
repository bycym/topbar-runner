# Packaging

Portable builds use PyInstaller from the optional Poetry `build` group. Runtime dependencies stay in the main group.

Run `Build and release` manually in GitHub Actions. Each run tests all platforms, builds and smoke tests each native app, and saves Apple Silicon and Intel macOS and Ubuntu `.tar.gz` archives plus a Windows `.zip` archive as workflow artifacts. On macOS, choose `macos-arm64` for Apple Silicon or `macos-x64` for Intel. Select `Publish a GitHub Release` and enter a version tag such as `v0.1.0` to publish those archives. An existing tag must point to the selected commit; if absent, publication creates it at that commit. The Ubuntu runner installs Qt's required system libraries, including `libegl1`, before tests and packaging.

Portable apps run Python plugins with a separate `python3` or `python` executable found on `PATH`; users need Python installed. A plugin can override its interpreter in metadata. On macOS and Linux, shell plugins use `bash`.

## macOS

```bash
poetry install --with build
poetry run pyinstaller packaging/pyinstaller/topbar-runner.spec
```

Output:

- `dist/topbar-runner.app`

The release workflow builds `macos-arm64` on macOS 14 and `macos-x64` on macOS 15. After extracting the matching archive, open `topbar-runner.app`. If the icon disappears at launch, run `topbar-runner.app/Contents/MacOS/topbar-runner --debug` from Terminal to see the startup error.

## Linux

```bash
poetry install --with build
poetry run pyinstaller packaging/pyinstaller/topbar-runner.spec
```

Output:

- `dist/topbar-runner/topbar-runner`

AppImage packaging can wrap that directory with `appimagetool`.

## Windows

```powershell
poetry install --with build
poetry run pyinstaller packaging\pyinstaller\topbar-runner.spec
```

Output:

- `dist\topbar-runner\topbar-runner.exe`

## Smoke Test

After building, run:

```bash
dist/topbar-runner/topbar-runner --console --plugin-dir examples/plugins
```
