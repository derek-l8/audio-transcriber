"""Prepare continuous Yale lecture chapters from locally downloaded sources.

Keep the source MP3s, HTML transcripts, and text-bearing manifest in an
ignored directory. This does not certify the transcript against the audio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import wave
from html.parser import HTMLParser
from pathlib import Path

SOURCES = (
    {
        "stem": "phys200-09",
        "chapter": 1,
        "next_chapter": 2,
        "id": "yale-phys200-rigid-bodies",
        "page": "https://oyc.yale.edu/physics/phys-200/lecture-9",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/fall06/phys200/mp3/phys200_09_100906.mp3",
        "mp3_sha256": "6252b457c4aaefa7c90896ad74fadbbcf76f0f43aa3466f911e7bc46ddcfdf79",
        "html_sha256": "62e0ef9885495370d0bfd5293d72d341ea57f7ab81f3cb1cf8bd1ca307d630e5",
    },
    {
        "stem": "astr160-01",
        "chapter": 2,
        "next_chapter": 3,
        "id": "yale-astr160-course-topics",
        "page": "https://oyc.yale.edu/astronomy/astr-160/lecture-1",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/spring07/astr160/mp3/astr160_01_011607.mp3",
        "mp3_sha256": "19304bbeea52c64f03af6aaeef9d5bc5b0a08772b59f50749897027268a03314",
        "html_sha256": "6c64e14a014659eba61ac8444292998f9da6d638c2df802129706626b0d69db8",
    },
    {
        "stem": "chem125a-10",
        "chapter": 1,
        "next_chapter": 2,
        # The MP3 reaches the chapter-2 opening around 580 s, about 267 s
        # before the page's video chapter marker. This is ASR-assisted alignment.
        "audio_end_override": 580,
        "id": "yale-chem125a-orbital-plots",
        "page": "https://oyc.yale.edu/chemistry/chem-125a/lecture-10",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/fall08/chem125/mp3/chem125_10_092408.mp3",
        "mp3_sha256": "2e2fb076b583f116a957d76f78a2d3e46df45526dda8c82d096ba4019bb72653",
        "html_sha256": "1351a35f2595992ec960c35619fdabd65bdc7c77904e584c5a733110bed45f08",
    },
)
CHAPTER = re.compile(r"<h3>Chapter (\d+)\. .*?\[(\d\d):(\d\d):(\d\d)\]</h3>", re.DOTALL)
HOLDOUT_SOURCES = (
    {
        "stem": "beng100-01",
        "chapter": 4,
        "next_chapter": 5,
        "audio_start_override": 1368.4,
        "audio_end_override": 1859.02,
        "id": "holdout-beng100-disease-control",
        "page": "https://oyc.yale.edu/biomedical-engineering/beng-100/lecture-1",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/spring08/beng100/mp3/beng100_01_011508.mp3",
        "mp3_sha256": "ea0e62b1581b43602f064b79f20e1a7c29d7668b85155a232d87a7760c0840c6",
        "html_sha256": "b94ebdaf4a3212d4b2d27b7aa46db331254714a08a2ded1fb48c301e821eb72d",
    },
    {
        "stem": "psyc110-02",
        "chapter": 2,
        "next_chapter": 3,
        "audio_start_override": 714.62,
        "audio_end_override": 1157.22,
        "id": "holdout-psyc110-neuroscience",
        "page": "https://oyc.yale.edu/psychology/psyc-110/lecture-2",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/spring07/psyc110/mp3/psyc110_02_012207.mp3",
        "mp3_sha256": "7f74b3321b348ce4acef8212133b4d5fe7ad4d0febe10cf2205d499edb549284",
        "html_sha256": "ef07a73282bc34fd8005d65cad16d966eecb4721aa5579f4091989843822d95d",
    },
    {
        "stem": "mcdb150-01",
        "chapter": 1,
        "next_chapter": 2,
        "id": "holdout-mcdb150-population-biology",
        "page": "https://oyc.yale.edu/molecular-cellular-and-developmental-biology/mcdb-150/lecture-1",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/spring09/mcdb150/mp3/mcdb150_01_011309.mp3",
        "mp3_sha256": "0a7040df7d2204618b01034d8e5e06f021d4772ef929e974a3855973d0fa5863",
        "html_sha256": "977db13101629aa1332487b2d0e018a8b43ac6bff03b19c46c3bc25f70d49634",
    },
)
SPEAKER = re.compile(r"\b(?:Professor [^:]{1,80}|Students?):\s*")
REFINEMENT_SOURCES = (
    {
        "stem": "eeb122-01",
        "chapter": 3,
        "next_chapter": 4,
        "id": "new-eeb122-natural-selection",
        "page": "https://oyc.yale.edu/ecology-and-evolutionary-biology/eeb-122/lecture-1",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/spring09/eeb122/mp3/eeb122_01_011209.mp3",
        "mp3_sha256": "3e097aee09a19d8ca03595f7e68a098aaa3b06678ad990ea384f81e745540098",
        "html_sha256": "386a44800f1c05f949a5e2efc46afe330682c2cb679efb611347635b55331706",
    },
    {
        "stem": "econ159-01",
        "chapter": 5,
        "next_chapter": 6,
        "id": "new-econ159-dominant-strategies",
        "page": "https://oyc.yale.edu/economics/econ-159/lecture-1",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/fall07/econ159/mp3/econ159_01_090507.mp3",
        "mp3_sha256": "90a6f59d05cdc9b3ed96cbbcb0438afe9500676f8d94ebd94efa4bc4f8bf41d9",
        "html_sha256": "80fda2720e78c47845e23c48a70be4a5f91b3dac807a859d776fc09f57f1a9e0",
    },
    {
        "stem": "phil176-02",
        "chapter": 2,
        "next_chapter": 3,
        "reference_start_phrase": "As I said, it looks as though",
        "id": "new-phil176-self-identity",
        "page": "https://oyc.yale.edu/philosophy/phil-176/lecture-2",
        "audio": "https://oyc.yale.edu/sites/default/files/courses/spring07/phil176/mp3//phil176_02_011807.mp3",
        "mp3_sha256": "68c96035fd44cb0fbe3408838387f04e7785d0e24f468c4d388a2b5be6304d62",
        "html_sha256": "69bc6914b07995158d3352937cccf639f845ed5e426e34591e43ce061feb03c5",
    },
)
EDITORIAL = re.compile(r"\[[^\]]{1,200}\]")


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "br", "div"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seconds(match: re.Match[str]) -> int:
    return int(match[2]) * 3600 + int(match[3]) * 60 + int(match[4])


def chapter_reference(html: str, chapter: int, next_chapter: int) -> tuple[int, int, str]:
    markers = {int(m[1]): m for m in CHAPTER.finditer(html)}
    first, following = markers[chapter], markers[next_chapter]
    fragment = html[first.end() : following.start()]
    extractor = PlainText()
    extractor.feed(fragment)
    reference = SPEAKER.sub("", "".join(extractor.parts))
    reference = EDITORIAL.sub("", reference)
    reference = re.sub(r"\s+", " ", reference).strip()
    if len(reference.split()) < 300:
        raise ValueError(f"Chapter {chapter} reference is unexpectedly short")
    return seconds(first), seconds(following), reference


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument(
        "--source-set", choices=("initial", "holdout", "refinement"), default="initial"
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    selected = {"initial": SOURCES, "holdout": HOLDOUT_SOURCES, "refinement": REFINEMENT_SOURCES}[
        args.source_set
    ]
    for source in selected:
        stem = source["stem"]
        mp3 = args.source_dir / f"{stem}.mp3"
        page = args.source_dir / f"{stem}.html"
        if sha256(mp3) != source["mp3_sha256"] or sha256(page) != source["html_sha256"]:
            raise ValueError(f"Source checksum mismatch: {stem}")
        start, published_end, reference = chapter_reference(
            page.read_text(encoding="utf-8"), source["chapter"], source["next_chapter"]
        )
        if source.get("reference_start_phrase"):
            phrase = str(source["reference_start_phrase"])
            if phrase not in reference:
                raise ValueError(f"Reference start phrase is missing: {stem}")
            reference = reference[reference.index(phrase) :]
        published_start = start
        start = source.get("audio_start_override", published_start)
        end = source.get("audio_end_override", published_end)
        wav = args.output_dir / f"{source['id']}.wav"
        subprocess.run(  # noqa: S603 - explicit executable and argv; no shell
            [
                str(args.ffmpeg),
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(mp3),
                "-ss",
                str(start),
                "-to",
                str(end),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(wav),
            ],
            check=True,
        )
        with wave.open(str(wav), "rb") as recording:
            duration = recording.getnframes() / recording.getframerate()
        if abs(duration - (end - start)) > 0.1:
            raise ValueError(f"Unexpected decoded duration: {stem} {duration}")
        cases.append(
            {
                "id": source["id"],
                "audio_url": wav.resolve().as_uri(),
                "audio_sha256": sha256(wav),
                "expected_size_bytes": wav.stat().st_size,
                "license": "CC BY-NC-SA 3.0, Yale Open Courses; local noncommercial evaluation",
                "official_source": source["page"],
                "source_audio_url": source["audio"],
                "reference_text": reference,
                "reference_provenance": (
                    "Yale Open Courses chapter transcript; Yale does not document "
                    "word-level audio verification"
                ),
                "preparation": (
                    f"MP3 SHA-256 {source['mp3_sha256']}; HTML SHA-256 "
                    f"{source['html_sha256']}; chapter {source['chapter']} "
                    f"{start}-{end}s "
                    f"(published chapter bounds {published_start}-{published_end}s); "
                    + (
                        "ASR-assisted boundary alignment before overlap comparison; "
                        if "audio_start_override" in source or "audio_end_override" in source
                        else ""
                    )
                    + "FFmpeg mono 16 kHz PCM"
                    + (
                        "; ASR-assisted gross alignment; reference starts at an original "
                        "transcript paragraph because the published chapter marker "
                        "falls inside the chapter in the MP3; not listening-verified"
                        if source.get("reference_start_phrase")
                        else ""
                    )
                ),
                "audio_seconds": round(duration, 5),
            }
        )
    manifest = {
        "schema_version": 1,
        "name": {
            "initial": "Yale continuous physics astronomy and chemistry chapters",
            "holdout": "Yale held-out biomedical engineering neuroscience and biology chapters",
            "refinement": "New Yale natural selection game theory and philosophy passages",
        }[args.source_set],
        "cases": cases,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for case in cases:
        print(case["id"], case["audio_seconds"], len(case["reference_text"].split()))


if __name__ == "__main__":
    main()
