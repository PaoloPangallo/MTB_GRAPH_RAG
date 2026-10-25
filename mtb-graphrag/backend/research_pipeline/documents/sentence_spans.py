"""Conservative sentence boundaries, retaining offsets into the input text."""
import re

VERSION = "biomedical-sentence-spans/1.0"
_ABBREVIATIONS = frozenset({"dr", "mr", "mrs", "ms", "prof", "fig", "figs", "eq", "eqs", "ref", "refs", "al", "vs", "approx", "no", "nos", "vol", "e.g", "i.e"})


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    for match in re.finditer(r"[.!?]+[\"')\]]*(?=\s|$)", text):
        punctuation = match.start()
        if text[punctuation] == '.':
            prefix = re.search(r"([\w.]+)$", text[:punctuation])
            if prefix and prefix.group(1).lower() in _ABBREVIATIONS:
                continue
        end = match.end()
        left = start
        while left < end and text[left].isspace():
            left += 1
        if left < end:
            spans.append((left, end))
        start = end
    left = start
    while left < len(text) and text[left].isspace():
        left += 1
    right = len(text.rstrip())
    if left < right:
        spans.append((left, right))
    return spans
