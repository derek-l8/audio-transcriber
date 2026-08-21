from __future__ import annotations

import json
from dataclasses import asdict

from .models import SCHEMA_VERSION, Transcript


def plain_text(transcript: Transcript) -> str:
    return transcript.text + "\n"


def markdown(transcript: Transcript, title: str) -> str:
    lines = [f"# {title}", ""]
    lines.extend(f"- [{_stamp(s.start)}] {s.text}" for s in transcript.segments)
    return "\n".join(lines) + "\n"


def srt(transcript: Transcript) -> str:
    blocks = [
        f"{i}\n{_srt_stamp(s.start)} --> {_srt_stamp(s.end)}\n{s.text.strip()}"
        for i, s in enumerate(transcript.segments, 1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def structured_json(transcript: Transcript, layer: str) -> str:
    value = {
        "schema_version": SCHEMA_VERSION,
        "layer": layer,
        "created_at": transcript.created_at,
        "provenance": asdict(transcript.provenance),
        "segments": [asdict(segment) for segment in transcript.segments],
    }
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _stamp(seconds: float) -> str:
    minutes, second = divmod(int(seconds), 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02}:{minute:02}:{second:02}"


def _srt_stamp(seconds: float) -> str:
    whole = int(seconds)
    millis = round((seconds - whole) * 1000)
    return f"{_stamp(whole)},{millis:03}"
