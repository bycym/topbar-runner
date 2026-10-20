# PyInstaller spec for portable topbar-runner builds.

from pathlib import Path
import sys

ROOT = Path.cwd()


a = Analysis(
    [str(ROOT / "topbar_runner" / "cli.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "examples" / "plugins"), "examples/plugins")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="topbar-runner",
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="topbar-runner",
)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="topbar-runner.app",
        icon=None,
        bundle_identifier="com.local.topbar-runner",
    )
