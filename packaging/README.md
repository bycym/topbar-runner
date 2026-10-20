# Packaging

Portable builds use PyInstaller from the optional Poetry `build` group. Runtime dependencies stay in the main group.

Run `Build and release` manually in GitHub Actions. Each run tests all platforms, builds and smoke tests each native app, and saves Apple Silicon and Intel macOS and Ubuntu `.tar.gz` archives plus a Windows `.zip` archive as workflow artifacts. On macOS, choose `apple-silicon` for Apple Silicon or `intel` for Intel. Select `Publish a GitHub Release` and leave `release_tag` empty to advance the highest numeric `v` tag. Dotted tags increment their last number; a whole-number tag starts a new series, so after `v1.3`, a manual `v2` makes the next automatic release `v2.1`. Nonnumeric tags are ignored for automatic numbering. With no numeric tags, the first release is `v0.1.0`. An existing tag must point to the selected commit; if absent, publication creates it at that commit. The Ubuntu runner installs Qt's required system libraries, including `libegl1`, before tests and packaging.

Portable apps run Python plugins with a separate `python3` or `python` executable found on `PATH`; users need Python installed. A plugin can override its interpreter in metadata. On macOS and Linux, shell plugins use `bash`.

## macOS

```bash
poetry install --with build
poetry run pyinstaller packaging/pyinstaller/topbar-runner.spec
```

Output:

- `dist/topbar-runner.app`

The release workflow builds `topbar-runner-<label>-apple-silicon.tar.gz` on macOS 14 and `topbar-runner-<label>-intel.tar.gz` on macOS 15. After extracting the matching archive, open `topbar-runner.app`. If the icon disappears at launch, run `topbar-runner.app/Contents/MacOS/topbar-runner --debug` from Terminal to see the startup error.

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

Extract the entire Windows ZIP before running `topbar-runner\topbar-runner.exe`. Keep its `_internal` folder beside the executable; that folder includes `python313.dll` and other bundled runtime files. Python plugins still need a separate Python installation on `PATH`.

## Smoke Test

After building on macOS or Linux, run:

```bash
dist/topbar-runner/topbar-runner --console --plugin-dir examples/plugins
```

On Windows, extract the ZIP and run:

```powershell
.\topbar-runner\topbar-runner.exe --console --plugin-dir examples\plugins
```
