"""Build a local TED-LIUM long-form manifest from cached dataset-server rows.

Fetch the validation/test row JSON from distil-whisper/tedlium-long-form and
download the selected audio files to the same directory before running this.
The source audio, text-bearing row JSON, and manifest must stay outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path

DATASET = "https://huggingface.co/datasets/distil-whisper/tedlium-long-form"
SPEAKERS = (
    ("validation", "Blaise_Agueray_Arcas"),
    ("validation", "Brian_Cox"),
    ("test", "GaryFlake"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    cases = []
    for split, speaker in SPEAKERS:
        data = json.loads((args.data_dir / f"{split}.json").read_text(encoding="utf-8"))
        matches = [entry for entry in data["rows"] if entry["row"]["speaker_id"] == speaker]
        if len(matches) != 1:
            raise ValueError(f"Expected one {split} row for {speaker}")
        entry = matches[0]
        audio = args.data_dir / f"{split}-{speaker}.wav"
        with wave.open(str(audio), "rb") as recording:
            if recording.getnchannels() != 1 or recording.getframerate() != 16000:
                raise ValueError(f"Unsupported WAV format: {audio}")
            seconds = recording.getnframes() / recording.getframerate()
        cases.append(
            {
                "id": f"tedlium-{split}-{speaker.lower()}",
                "audio_url": audio.resolve().as_uri(),
                "audio_sha256": sha256(audio),
                "expected_size_bytes": audio.stat().st_size,
                "license": "CC BY-NC-ND 3.0; local noncommercial evaluation only",
                "official_source": DATASET,
                "reference_text": entry["row"]["text"],
                "reference_provenance": (
                    "TED-LIUM release 3 manual dev/test transcript, merged by "
                    "distil-whisper/tedlium-long-form"
                ),
                "preparation": (
                    f"Dataset {split} row {entry['row_idx']}; source utterances "
                    "concatenated into long-form audio by dataset maintainer"
                ),
                "audio_seconds": round(seconds, 5),
            }
        )
    manifest = {"schema_version": 1, "name": "tedlium-manual-talk-pilot", "cases": cases}
    (args.data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Prepared {len(cases)} talks, {sum(c['audio_seconds'] for c in cases):.2f} seconds")
    for case in cases:
        print(case["id"], case["audio_sha256"])


if __name__ == "__main__":
    main()
