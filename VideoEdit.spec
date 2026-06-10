# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


datas = []
binaries = []
hiddenimports = []

for package_name in ('rembg', 'onnxruntime', 'pymatting'):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

tbb_bin_dir = Path.cwd() / '.venv314' / 'Library' / 'bin'
for dll_name in (
    'libhwloc-15.dll',
    'tbb12.dll',
    'tbbbind.dll',
    'tbbbind_2_0.dll',
    'tbbbind_2_5.dll',
    'tbbmalloc.dll',
    'tbbmalloc_proxy.dll',
    'tcm.dll',
):
    dll_path = tbb_bin_dir / dll_name
    if dll_path.exists():
        binaries.append((str(dll_path), '.'))


a = Analysis(
    ['VideoEdit.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

a.binaries = [
    binary
    for binary in a.binaries
    if Path(binary[0]).name.lower() != 'msvcp140.dll'
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VideoEdit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
