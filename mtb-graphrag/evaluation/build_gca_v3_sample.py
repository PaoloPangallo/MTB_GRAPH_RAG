"""Campione stratificato v3 per la revisione umana (§20).

Uso::

    python -m evaluation.build_gca_v3_sample

75 record, deterministici. Le colonne del revisore restano **vuote**: nessun
giudizio umano viene precompilato e nessun output automatico vi viene scritto.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
V3 = (REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
      / "graph_candidate_repository" / "3.0" / "candidates.jsonl")
OUT = REPO_ROOT / "evaluation" / "gold" / "rq1_gca_v3_manual_review.csv"

FIELDS = [
    "candidate_v3_id", "stratum", "source_path_id", "disease",
    "graph_direction", "source_support_polarity", "source_supported_direction",
    "source_alignment_status",
    "alteration_raw", "alteration_ast", "alteration_parse_status",
    "intervention_raw", "intervention_components", "intervention_structure",
    "regimen_semantics_status", "automatic_findings",
    # Annotazione umana — deve restare vuota.
    "reviewer_semantic_fidelity", "reviewer_polarity_correct",
    "reviewer_alteration_correct", "reviewer_regimen_correct", "reviewer_notes",
]

#: Strati richiesti dal protocollo, con la quota prevista.
STRATA: "OrderedDict[str, tuple]" = OrderedDict([
    ("source_aligned_simple", (15, lambda c: (
        c["source_alignment_status"] == "SOURCE_ALIGNED"
        and c["alteration_parse_status"] == "ATOMIC"
        and c["intervention_structure"] == "SINGLE_AGENT"))),
    ("does_not_support", (15, lambda c: c["source_alignment_status"] == "SOURCE_DOES_NOT_SUPPORT")),
    ("neutral_no_difference", (10, lambda c: c["source_alignment_status"] == "SOURCE_NEUTRAL")),
    ("compound_alteration", (15, lambda c: c["alteration_parse_status"] in
                             {"PARSED_EXACT", "PARSED_WITH_WARNINGS"})),
    ("multi_drug", (15, lambda c: c["intervention_structure"] == "MULTI_COMPONENT_UNRESOLVED")),
    ("unparsable_or_ambiguous", (5, lambda c: (
        c["alteration_parse_status"] in {"MALFORMED_EXPRESSION", "UNSUPPORTED_EXPRESSION",
                                         "AMBIGUOUS_OPERATOR"}
        or c["source_alignment_status"] == "SOURCE_ALIGNMENT_UNCLEAR"
        or c["alteration_parse_warnings"]))),
])


def _findings(candidate: dict) -> str:
    out = []
    if candidate["source_alignment_status"] == "SOURCE_DOES_NOT_SUPPORT":
        out.append("SOURCE_DOES_NOT_SUPPORT")
    if candidate["intervention_structure"] == "MULTI_COMPONENT_UNRESOLVED":
        out.append("REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT")
    if candidate["alteration_parse_status"] in {"PARSED_EXACT", "PARSED_WITH_WARNINGS"}:
        out.append(f"COMPOUND_ALTERATION:{len(candidate['alteration_terms'])}_TERMS")
    out.extend(candidate["alteration_parse_warnings"])
    return "|".join(out) or "NONE"


def main() -> int:
    candidates = [json.loads(line) for line in
                  V3.read_text(encoding="utf-8").splitlines() if line.strip()]
    ordered = sorted(candidates, key=lambda c: c["candidate_id"])

    selected: "OrderedDict[str, tuple[dict, str]]" = OrderedDict()
    shortfall: dict[str, int] = {}
    for name, (quota, predicate) in STRATA.items():
        taken = 0
        for candidate in ordered:
            if taken >= quota:
                break
            if candidate["candidate_id"] in selected:
                continue
            if predicate(candidate):
                selected[candidate["candidate_id"]] = (candidate, name)
                taken += 1
        if taken < quota:
            shortfall[name] = quota - taken

    rows = []
    for candidate, stratum in selected.values():
        rows.append({
            "candidate_v3_id": candidate["candidate_id"],
            "stratum": stratum,
            "source_path_id": "|".join(candidate["source_path_ids"][:4]),
            "disease": "|".join(str(d.get("label")) for d in candidate["disease"]),
            "graph_direction": candidate["graph_direction"],
            "source_support_polarity": candidate["source_support_polarity"],
            "source_supported_direction": candidate["source_supported_direction"] or "",
            "source_alignment_status": candidate["source_alignment_status"],
            "alteration_raw": candidate["alteration_expression_raw"] or "",
            "alteration_ast": json.dumps(candidate["alteration_expression_ast"],
                                         ensure_ascii=False)[:600]
                              if candidate["alteration_expression_ast"] else "",
            "alteration_parse_status": candidate["alteration_parse_status"],
            "intervention_raw": candidate["intervention_expression_raw"] or "",
            "intervention_components": "|".join(
                str(c.get("name")) for c in candidate["intervention_components"]),
            "intervention_structure": candidate["intervention_structure"],
            "regimen_semantics_status": candidate["regimen_semantics_status"],
            "automatic_findings": _findings(candidate),
            "reviewer_semantic_fidelity": "",
            "reviewer_polarity_correct": "",
            "reviewer_alteration_correct": "",
            "reviewer_regimen_correct": "",
            "reviewer_notes": "",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["stratum"]] = counts.get(row["stratum"], 0) + 1
    blank = all(not row[c] for row in rows for c in FIELDS[-5:])
    print(f"[v3-sample] righe: {len(rows)} -> {OUT.relative_to(REPO_ROOT)}")
    print("[v3-sample] strati:", json.dumps(counts, indent=1))
    if shortfall:
        print("[v3-sample] strati non riempibili (popolazione insufficiente):", shortfall)
    print(f"[v3-sample] colonne revisore vuote: {blank}")
    return 0 if blank else 1


if __name__ == "__main__":
    sys.exit(main())
