"""Make a local, traceable AMI meeting accuracy pilot from official downloads.

The output directory contains corpus audio and transcripts. Keep it outside Git.
Download ami_public_manual_1.6.2.zip and the two Mix-Headset WAVs from
https://groups.inf.ed.ac.uk/ami/download/ before running this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import wave
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SOURCE = "https://groups.inf.ed.ac.uk/ami/download/"
EXPECTED_SHA256 = {
    "manual.zip": "b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d",
    "ES2004a.Mix-Headset.wav": "3e2560b19bee6952c7c7ce041b0f1ea8a7ea9468044c4eea79d2a2c67e24ab0f",
    "ES2014a.Mix-Headset.wav": "9d29e308566b8c7be4c328f4a2998e371e5f506384f111042ec91b465f7f792c",
}
CLIPS = (("ES2004a", 720, 840), ("ES2004a", 840, 960), ("ES2014a", 720, 840), ("ES2014a", 840, 960))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def reference(archive: zipfile.ZipFile, meeting: str, start: int, end: int) -> str:
    words: list[tuple[float, str, str]] = []
    for speaker in "ABCD":
        # Archive SHA-256 is checked against the pinned official download first.
        root = ET.fromstring(archive.read(f"words/{meeting}.{speaker}.words.xml"))  # noqa: S314
        for element in root:
            if element.tag != "w" or element.get("punc") or not element.text:
                continue
            word_start = float(element.attrib["starttime"])
            word_end = float(element.attrib["endtime"])
            if start <= word_start and word_end <= end:
                words.append((word_start, speaker, element.text))
    words.sort()
    return " ".join(word for _, _, word in words)


def crop_wav(source: Path, destination: Path, start: int, end: int) -> None:
    with wave.open(str(source), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getframerate() != 16000:
            raise ValueError(f"Unsupported WAV format: {source}")
        rate = audio.getframerate()
        if audio.getnframes() < end * rate:
            raise ValueError(f"WAV is too short for {end}s crop: {source}")
        audio.setpos(start * rate)
        frames = audio.readframes((end - start) * rate)
        with wave.open(str(destination), "wb") as output:
            output.setparams(audio.getparams())
            output.writeframes(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = args.input_dir / "manual.zip"
    sources = {meeting: args.input_dir / f"{meeting}.Mix-Headset.wav" for meeting, _, _ in CLIPS}
    source_checksums = {path.name: sha256(path) for path in (archive_path, *sources.values())}
    if source_checksums != EXPECTED_SHA256:
        raise ValueError("AMI source checksums do not match the pinned pilot inputs")
    cases = []
    with zipfile.ZipFile(archive_path) as archive:
        for meeting, start, end in CLIPS:
            case_id = f"ami-{meeting.lower()}-{start}-{end}"
            clip = args.output_dir / f"{case_id}.wav"
            crop_wav(sources[meeting], clip, start, end)
            cases.append(
                {
                    "id": case_id,
                    "audio_url": clip.resolve().as_uri(),
                    "audio_sha256": sha256(clip),
                    "expected_size_bytes": clip.stat().st_size,
                    "license": "CC BY 4.0",
                    "official_source": SOURCE,
                    "reference_text": reference(archive, meeting, start, end),
                    "reference_provenance": (
                        "AMI manual annotations v1.6.2; human first and second passes; "
                        "word timings from forced alignment; all four speakers"
                    ),
                    "preparation": f"{meeting} Mix-Headset WAV, exact {start}-{end}s crop",
                    "audio_seconds": end - start,
                }
            )
    manifest = {"schema_version": 1, "name": "ami-manual-test-pilot", "cases": cases}
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "source-sha256.json").write_text(
        json.dumps(source_checksums, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared {len(cases)} clips, {sum(c['audio_seconds'] for c in cases)} seconds")
    print(f"Source SHA-256: {source_checksums}")


if __name__ == "__main__":
    main()
