# Experimental Windows recipe; see packaging/README.md before redistribution.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

root = Path(SPECPATH).parent
ov_data, ov_bins, ov_hidden = collect_all("openvino")
genai_data, genai_bins, genai_hidden = collect_all("openvino_genai")
# GenAI loads this extension dynamically; import analysis does not collect its DLL.
tokenizer_bins = collect_dynamic_libs("openvino_tokenizers")
notice_data = [
    (str(root / "LICENSE"), "licenses"),
    (str(root / "THIRD_PARTY_NOTICES.md"), "licenses"),
]

a = Analysis(
    [str(root / "packaging" / "desktop_entry.py")],
    pathex=[str(root / "src")],
    binaries=ov_bins + genai_bins + tokenizer_bins,
    datas=ov_data + genai_data + notice_data,
    hiddenimports=ov_hidden + genai_hidden,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NPU Scribe", console=False)

worker = Analysis(
    [str(root / "packaging" / "worker_entry.py")],
    pathex=[str(root / "src")],
    binaries=ov_bins + genai_bins + tokenizer_bins,
    datas=ov_data + genai_data + notice_data,
    hiddenimports=ov_hidden + genai_hidden,
)
worker_pyz = PYZ(worker.pure)
worker_exe = EXE(
    worker_pyz, worker.scripts, [], exclude_binaries=True,
    name="npu-scribe-worker", console=True,
)
coll = COLLECT(
    exe, worker_exe, a.binaries, a.datas, worker.binaries, worker.datas,
    name="NPU Scribe",
)
