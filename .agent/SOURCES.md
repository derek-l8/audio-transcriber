# Primary source inventory

Accessed 2026-08-21. Artifacts are not redistributed unless explicitly stated.

| Source | Supports | Version/license relevance |
|---|---|---|
| [OpenVINO GenAI on NPU](https://docs.openvino.ai/2026/openvino-workflow-generative/inference-with-genai/inference-with-genai-on-npu.html) | Whisper supports CPU/GPU/NPU; conversion and NPU driver guidance | OpenVINO 2026.3; code packages Apache-2.0; model licenses separate |
| [OpenVINO GenAI inference](https://docs.openvino.ai/2026/openvino-workflow-generative/inference-with-genai.html) | `WhisperPipeline(model_dir, device)`, 16 kHz normalized input, timestamps | 2026 docs |
| [Qt for Python](https://doc.qt.io/qtforpython-6/index.html) | Official Python bindings and deployment option | PySide6 LGPLv3/GPLv3/commercial; comply with LGPL for dynamic distribution |
| [QSystemTrayIcon](https://doc.qt.io/qtforpython-6.10/PySide6/QtWidgets/QSystemTrayIcon.html) | Windows tray support and notifications | Qt 6.10 docs |
| [Qt Multimedia](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/index.html) | Microphone recording and playback APIs | Qt 6 docs; codec availability must be host-tested |
| [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) | UIPI blocks injection into higher-integrity targets; count indicates insertion | Windows SDK docs |
| [PyInstaller documentation](https://pyinstaller.org/_/downloads/en/v6.19.0/pdf/) | Windows/PySide packaging | PyInstaller 6.19, GPL-2.0 with exception |
| [OpenVINO whisper-tiny.en INT4 model card](https://huggingface.co/OpenVINO/whisper-tiny.en-int4-ov) | CPU feasibility model and GenAI invocation | Revision `2c4a4cb35a33f827f324c55f474d9197c586b485`; Apache-2.0; 21 deliverable files, kept in scratch only |

Bootstrap artifact used only in disposable scratch:
`get-pip.py`, SHA-256 `fb24e693bab954209a063d90953621412ccad4a500905a726286e038f508ddf6`,
downloaded from `https://bootstrap.pypa.io/get-pip.py`. It is not a deliverable.

Still to verify before redistribution: Inno Setup license/current version, FFmpeg build
license/configuration, each Python wheel license, every selected model manifest and model
license, and public evaluation dataset checksums/licenses.
