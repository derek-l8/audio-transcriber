from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import Mode

FILLERS = re.compile(r"\b(?:um+|uh+|erm|you know)\b[,.]?\s*", re.IGNORECASE)
REPETITION = re.compile(r"\b([\w'-]+)(?:\s+\1\b)+", re.IGNORECASE)
COMMANDS = {
    "new paragraph": "\n\n",
    "bullet point": "\n- ",
    "comma": ",",
    "period": ".",
    "question mark": "?",
    "open quote": "\u201c",
    "close quote": "\u201d",
}


@dataclass(frozen=True)
class ProcessedText:
    raw: str
    cleaned: str
    rewritten: str
    mode: Mode
    warnings: tuple[str, ...] = ()


def spoken_formatting(text: str) -> str:
    """Expand commands; `literal <command>` escapes exactly one command."""
    placeholders: dict[str, str] = {}
    for index, command in enumerate(COMMANDS):
        token = f"\x00{index}\x00"
        text = re.sub(rf"\bliteral\s+{re.escape(command)}\b", token, text, flags=re.I)
        placeholders[token] = command
    for command, value in COMMANDS.items():
        text = re.sub(rf"\b{re.escape(command)}\b", value, text, flags=re.I)
    for token, literal in placeholders.items():
        text = text.replace(token, literal)
    return re.sub(r"[ \t]+([,.?])", r"\1", text)


def deterministic_cleanup(text: str) -> str:
    text = text.strip()
    text = FILLERS.sub("", text)
    text = REPETITION.sub(r"\1", text)
    # Context-dependent self-corrections belong to the AI dictation mode.
    # The rule layer retains their source wording and ordinary technical words.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    text = re.sub(r"([,.?!])(?=\w)", r"\1 ", text)
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]
        if text[-1] not in ".?!\u201d":
            text += "."
    return text


def process_text(text: str, mode: Mode, semantic_rewriter: Any | None = None) -> ProcessedText:
    if mode == "raw":
        cleaned = spoken_formatting(text.strip())
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
    else:
        cleaned = deterministic_cleanup(text)
    rewritten = cleaned
    warnings: tuple[str, ...] = ()
    if mode == "aggressive" and semantic_rewriter is not None:
        rewritten = str(semantic_rewriter.rewrite(cleaned, mode))
        if _numbers(text) != _numbers(rewritten) or _negation_changed(text, rewritten):
            warnings = ("semantic-risk: number or negation changed; using deterministic result",)
            rewritten = cleaned
    return ProcessedText(text, cleaned, rewritten, mode, warnings)


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))


def _negation_changed(before: str, after: str) -> bool:
    pattern = r"\b(?:no|not|never|n't)\b"
    return len(re.findall(pattern, before, re.I)) != len(re.findall(pattern, after, re.I))
