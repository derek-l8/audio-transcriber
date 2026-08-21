from __future__ import annotations


def _distance(left: list[str], right: list[str]) -> int:
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        next_row = [i]
        for j, b in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = next_row
    return row[-1]


def wer(reference: str, hypothesis: str) -> float:
    words = reference.casefold().split()
    return _distance(words, hypothesis.casefold().split()) / max(1, len(words))


def cer(reference: str, hypothesis: str) -> float:
    chars = list(reference.casefold())
    return _distance(chars, list(hypothesis.casefold())) / max(1, len(chars))
