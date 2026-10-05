"""Keep Qt Widgets plugins without unused PDF and virtual-keyboard backends."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [
    item
    for item in binaries
    if Path(item[0]).name.lower() not in {"qtvirtualkeyboardplugin.dll", "qpdf.dll"}
]
