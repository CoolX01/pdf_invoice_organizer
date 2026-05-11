# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


tools_dir = Path(SPECPATH).resolve()
project_dir = tools_dir.parent
source_dir = project_dir / "source"
datas = [
    (str(source_dir / "config" / "default_settings.json"), "config"),
    (str(source_dir / "config" / "user_settings.example.json"), "config"),
    (str(source_dir / "assets"), "assets"),
]
hiddenimports = [
    "qt_compat",
]

for package_name in ("rapidocr_onnxruntime", "pdfplumber"):
    try:
        hiddenimports += collect_submodules(package_name)
        datas += collect_data_files(package_name)
    except Exception:
        pass

try:
    hiddenimports += collect_submodules("paddleocr")
    datas += collect_data_files("paddleocr")
except Exception:
    pass


a = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir), str(source_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDF发票自动整理归纳工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PDF发票自动整理归纳工具",
)
