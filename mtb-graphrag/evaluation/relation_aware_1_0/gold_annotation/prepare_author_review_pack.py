"""Render a review-only author pack from frozen sources and AI_DRAFT files.

This script intentionally does not read or write annotation_primary.json,
annotation_review.json, or any runtime output.  Its only mutable outputs are
the two author-review artifacts beside this script.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ORDER = [
    "PAPER-05", "PAPER-08", "PAPER-12", "PAPER-14",
    "PAPER-01", "PAPER-02", "PAPER-03", "PAPER-06", "PAPER-09", "PAPER-13", "PAPER-15", "PAPER-16",
    "PAPER-04", "PAPER-07", "PAPER-10", "PAPER-11",
]
PRIORITY = {
    **{sample_id: "HIGH" for sample_id in ORDER[:4]},
    **{sample_id: "MEDIUM" for sample_id in ORDER[4:12]},
    **{sample_id: "LOW" for sample_id in ORDER[12:]},
}


def source_metadata(overview: str) -> dict[str, str]:
    labels = {
        "pmid": "PMID",
        "pmcid": "PMCID",
        "document_type": "Canonical document type",
        "title": "Title",
    }
    result = {}
    for key, label in labels.items():
        match = re.search(rf"- {re.escape(label)}: `([^`]*)`", overview)
        result[key] = (match.group(1) if match else "") or "NOT_AVAILABLE"
    return result


def disease_label(candidate: dict[str, object]) -> str:
    disease = candidate.get("disease", [])
    if not disease:
        return "NOT_AVAILABLE"
    labels = []
    for item in disease:
        label = item.get("label")
        if label and label not in labels:
            labels.append(label)
    return "; ".join(labels) or "NOT_AVAILABLE"


def unit_texts(markdown: str) -> dict[str, str]:
    pattern = re.compile(
        r"^## (?P<id>SU-[^\n]+)\n.*?^TEXT:\n\n(?P<text>.*?)(?=^## SU-|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    return {match["id"]: match["text"].strip() for match in pattern.finditer(markdown)}


def title_from_source_units(markdown: str) -> str:
    match = re.search(
        r"TYPE: `TITLE`\n.*?^TEXT:\n\n(?P<text>.*?)(?=^## SU-|\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    return match["text"].strip() if match else "NOT_AVAILABLE"


def main() -> None:
    decisions = []
    sections = [
        "# Author review pack — AI-assisted paper pre-annotations",
        "",
        "This document is for author review of AI_DRAFT annotations. It is not final gold. The author must decide independently whether to confirm or override each draft.",
        "",
        "## Consistency rules for author review",
        "",
        "- **FULL_SUPPORT**: all semantically necessary elements of the candidate are documented.",
        "- **PARTIAL_SUPPORT**: the core relation is documented, but a secondary specificity is missing (for example, a specific variant or disease subtype).",
        "- **NO_SUPPORT**: the document discusses a related context but does not support the specific core relation.",
        "- **CONTRADICTORY**: the document explicitly states the opposite of the candidate.",
        "- **UNVERIFIABLE**: the frozen material is insufficient for a reasoned decision.",
        "",
        "Important: if the polarity that defines the relation does not match or is missing (for example sensitivity versus resistance, or Supports versus Does Not Support), do not classify it automatically as PARTIAL_SUPPORT merely because gene or disease context coincide.",
        "",
        "## Review order",
        "",
        "High-priority cases first, then medium, then low. Sample identifiers remain unchanged.",
    ]

    for sample_id in ORDER:
        pack_dir = ROOT / sample_id
        candidate = json.loads((pack_dir / "candidate.json").read_text(encoding="utf-8"))
        overview = (pack_dir / "source_overview.md").read_text(encoding="utf-8")
        source_units_markdown = (pack_dir / "source_units.md").read_text(encoding="utf-8")
        source_units = unit_texts(source_units_markdown)
        ai_draft = json.loads((ROOT / "ai_drafts" / f"{sample_id}_ai_draft.json").read_text(encoding="utf-8"))
        assert candidate["candidate_id"] == ai_draft["candidate_id"]
        assert all(unit_id in source_units for unit_id in ai_draft["gold_source_unit_ids_draft"])
        assert any(
            ai_draft["gold_quote_draft"] in source_units[unit_id]
            for unit_id in ai_draft["gold_source_unit_ids_draft"]
        )
        source = source_metadata(overview)
        if source["title"] == "NOT_AVAILABLE":
            source["title"] = title_from_source_units(source_units_markdown)
        subject = candidate["subject"]["label"]
        obj = candidate["object"]["label"]
        sections += [
            "",
            f"## {sample_id}",
            "",
            f"Review priority: **{PRIORITY[sample_id]}**",
            "",
            "### Candidate",
            "",
            f"- candidate_id: `{candidate['candidate_id']}`",
            f"- disease: `{disease_label(candidate)}`",
            f"- subject: `{subject}`",
            f"- predicate: `{candidate['predicate']}`",
            f"- object: `{obj}`",
            f"- direction: `{candidate.get('direction', 'NOT_AVAILABLE')}`",
            f"- evidence_type: `{candidate.get('evidence_type', 'NOT_AVAILABLE')}`",
            "",
            "### Source",
            "",
            f"- PMID: `{source['pmid']}`",
            f"- PMCID: `{source['pmcid']}`",
            f"- document type: `{source['document_type']}`",
            f"- title: {source['title']}",
            "",
            "### AI draft fields",
            "",
            f"- disease: `{ai_draft['disease_supported']}`",
            f"- gene: `{ai_draft['gene_supported']}`",
            f"- alteration: `{ai_draft['alteration_supported']}`",
            f"- drug: `{ai_draft['drug_supported']}`",
            f"- direction: `{ai_draft['direction_supported']}`",
            f"- evidence_type: `{ai_draft['evidence_type_supported']}`",
            "",
            f"AI overall draft: **{ai_draft['overall_gold_draft']}**",
            "",
            f"Uncertainty: **{ai_draft['uncertainty']}**",
            "",
            "### Evidence used by AI draft",
            "",
            f"- SourceUnit IDs: {', '.join(f'`{unit_id}`' for unit_id in ai_draft['gold_source_unit_ids_draft'])}",
            f"- Literal quote: {ai_draft['gold_quote_draft']}",
            "",
            "### Reasoning",
            "",
            ai_draft["reasoning_summary"],
        ]
        if sample_id == "PAPER-01":
            sections += [
                "",
                "### Review flag",
                "",
                "General DICER1/disease context is present, but the specific D1709N alteration and Does Not Support polarity must be evaluated as part of the candidate's semantic core.",
            ]
        sections += [
            "",
            "### Author decision",
            "",
            "AUTHOR_DECISION=",
            "CONFIRM | OVERRIDE | PENDING",
            "",
            "AUTHOR_FINAL_LABEL=",
            "FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING",
            "",
            "AUTHOR_NOTES=",
        ]
        decisions.append(
            {
                "sample_id": sample_id,
                "ai_draft": ai_draft["overall_gold_draft"],
                "ai_uncertainty": ai_draft["uncertainty"],
                "author_decision": "PENDING",
                "author_final_label": "PENDING",
                "author_notes": "",
            }
        )

    (ROOT / "author_review_pack.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
    (ROOT / "author_review_decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
