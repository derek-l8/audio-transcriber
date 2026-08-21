from __future__ import annotations

import argparse
from pathlib import Path

from .engines import MockSpeechEngine, OpenVINOWhisperEngine
from .export import structured_json


def main() -> int:
    parser = argparse.ArgumentParser(prog="npu-scribe")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--device", default="CPU")
    args = parser.parse_args()
    engine = OpenVINOWhisperEngine(args.model) if args.model else MockSpeechEngine()
    print(structured_json(engine.transcribe(args.audio, args.device), "raw"), end="")
    return 0
