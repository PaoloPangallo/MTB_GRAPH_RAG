"""Literal composition checks; never infer a regimen from molecular context."""
from __future__ import annotations

import re

MOLECULAR_COMPOSITIONS = ("SINGLE", "COEXPRESSION", "COMBINATION", "CONDITIONAL", "ALTERNATIVES", "UNKNOWN")
INTERVENTION_COMPOSITIONS = ("SINGLE_AGENT", "COMBINATION", "UNKNOWN")


def intervention_composition_conflict(composition: str, intervention: str) -> bool:
    """Reject explicit grammar conflicts only; absence of a cue is not identity."""
    combination = re.search(r"\b(?:combination\s+(?:of|therapy)|combined\s+with|in\s+combination\s+with|plus)\b|\s\+\s", intervention, re.IGNORECASE)
    monotherapy = re.search(r"\b(?:monotherapy|alone|single[- ]agent)\b", intervention, re.IGNORECASE)
    return bool((composition == "SINGLE_AGENT" and combination)
                or (composition == "COMBINATION" and monotherapy and not combination))
