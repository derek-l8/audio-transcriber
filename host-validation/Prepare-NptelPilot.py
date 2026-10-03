"""Prepare a deterministic local NPTEL Pure Set evaluation manifest.

Download nptel-pure-set.tar.gz from the AI4Bharat NPTEL2020 v0.1 release.
The archive, WAVs, and text-bearing manifest belong in an ignored directory.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import wave
from pathlib import Path

SOURCE = (
    "https://github.com/AI4Bharat/NPTEL2020-Indian-English-Speech-Dataset/"
    "releases/download/v0.1/nptel-pure-set.tar.gz"
)
ARCHIVE_SHA256 = "cad8b68cce78adb4af2b432a2112d43c4c4425b0762564db20a03c3263bc051e"
COUNT = 100
TECHNICAL_TERMS = (
    "engineering",
    "physics",
    "chemistry",
    "mathematics",
    "computer",
    "electrical",
    "electronics",
    "mechanical",
    "aerospace",
    "civil",
    "material",
    "algorithm",
    "optics",
    "thermodynamics",
    "signal",
    "nano",
    "statistics",
    "probability",
    "biological",
    "biology",
    "chemical",
    "fluid",
    "robot",
    "machine",
    "geology",
)
EXCLUDE_TERMS = ("management", "finance", "economics", "english language")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_member(archive: tarfile.TarFile, name: str) -> bytes:
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"Missing archive member: {name}")
    return member.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    if sha256_bytes(args.archive.read_bytes()) != ARCHIVE_SHA256:
        raise ValueError("NPTEL archive SHA-256 does not match the pinned release")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "r:gz") as archive:
        candidates = []
        for member in archive:
            if not member.isfile() or not member.name.startswith("nptel-pure/metadata/"):
                continue
            stem = Path(member.name).stem
            metadata = json.loads(read_member(archive, member.name))
            video = metadata["metadata"]
            license_text = video.get("license") or ""
            topic = f"{video.get('title', '')} {video.get('description', '')}".casefold()
            reference = read_member(archive, f"nptel-pure/corrected_txt/{stem}.txt")
            reference_text = reference.decode("utf-8").strip()
            if (
                "Creative Commons Attribution" not in license_text
                or not 5 <= float(metadata["duration"]) <= 16
                or len(reference_text.split()) < 8
                or not any(term in topic for term in TECHNICAL_TERMS)
                or any(term in topic for term in EXCLUDE_TERMS)
            ):
                continue
            candidates.append((stem, metadata, reference_text))
        candidates.sort(key=lambda row: sha256_bytes(row[0].encode("ascii")))
        selected = []
        video_ids: set[str] = set()
        for row in candidates:
            video_id = row[1]["metadata"]["id"]
            if video_id in video_ids:
                continue
            selected.append(row)
            video_ids.add(video_id)
            if len(selected) == COUNT:
                break
        if len(selected) != COUNT:
            raise ValueError(f"Only {len(selected)} eligible distinct-video clips")
        cases = []
        for stem, metadata, reference_text in selected:
            content = read_member(archive, f"nptel-pure/wav/{stem}.wav")
            with wave.open(io.BytesIO(content), "rb") as recording:
                if recording.getnchannels() != 1 or recording.getframerate() != 16000:
                    raise ValueError(f"Unsupported NPTEL audio format: {stem}")
                duration = recording.getnframes() / recording.getframerate()
            if abs(duration - float(metadata["duration"])) > 0.05:
                raise ValueError(f"NPTEL duration mismatch: {stem}")
            audio = args.output_dir / f"nptel-{stem[:16]}.wav"
            audio.write_bytes(content)
            video = metadata["metadata"]
            cases.append(
                {
                    "id": f"nptel-{stem[:16]}",
                    "audio_url": audio.resolve().as_uri(),
                    "audio_sha256": sha256_bytes(content),
                    "expected_size_bytes": len(content),
                    "license": video["license"],
                    "official_source": SOURCE,
                    "source_video_url": video["webpage_url"],
                    "reference_text": reference_text,
                    "reference_provenance": (
                        "AI4Bharat NPTEL2020 Pure Set corrected_txt; authors report "
                        "manual annotation of the 1,000-clip sample"
                    ),
                    "preparation": (
                        f"v0.1 Pure Set archive WAV {stem}; original lecture timestamp "
                        f"{metadata['ts_start']} to {metadata['ts_end']}"
                    ),
                    "audio_seconds": round(duration, 5),
                }
            )
    manifest = {"schema_version": 1, "name": "nptel-pure-technical-100", "cases": cases}
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Prepared {len(cases)} clips from {len(video_ids)} videos")
    print(f"Audio: {sum(case['audio_seconds'] for case in cases):.2f} seconds")


if __name__ == "__main__":
    main()
