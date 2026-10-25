"""Literal fusion notation; interpreting a hyphen requires an explicit marker."""
import re

MARKERS = frozenset({'fusion', 'fusione'})


def explicit_partners(value: str, *, allow_hyphen: bool = False) -> tuple[str, ...]:
    value = value.strip()
    value = re.sub(r'^(?:fusion|fusione)\s+', '', value, flags=re.I)
    value = re.sub(r'\s+(?:fusion|fusione)$', '', value, flags=re.I)
    separator = r'(?:::|[-\u2010-\u2015])' if allow_hyphen else r'::'
    match = re.fullmatch(rf'([A-Za-z][A-Za-z0-9]*)\s*{separator}\s*([A-Za-z][A-Za-z0-9]*)', value)
    return tuple(part.upper() for part in match.groups()) if match else ()


def has_marker(value: str) -> bool:
    return bool(re.search(r'\b(?:fusion|fusione)\b', value, re.I))
