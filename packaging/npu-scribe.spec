# Build on Windows: pyinstaller --clean --noconfirm packaging/npu-scribe.spec
from PyInstaller.utils.hooks import collect_all

ov_data, ov_bins, ov_hidden = collect_all("openvino")
genai_data, genai_bins, genai_hidden = collect_all("openvino_genai")

a = Analysis(
    ["src/npu_scribe/desktop.py"],
    pathex=["src"],
    binaries=ov_bins + genai_bins,
    datas=ov_data + genai_data,
    hiddenimports=ov_hidden + genai_hidden,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NPU Scribe", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="NPU Scribe")
