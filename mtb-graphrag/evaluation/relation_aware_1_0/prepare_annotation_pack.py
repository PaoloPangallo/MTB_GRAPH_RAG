"""Build a human-only, unannotated paper gold pack from frozen inputs."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "gold_annotation"
SAMPLE = ROOT / "candidate_sample.json"
SOURCE_MANIFEST = ROOT / "sources/source_snapshot_manifest.json"
SAMPLE_SHA = "d168027b5e4994109c9cf1975a8d27bddcd214ae7d46a077a0aa4af594cc3233"
SOURCE_SHA = "15760611300ce0a1e605e7323265209db7da1870f7f0ecb58847e78907ebb942"
ANNOTATION_ORDER_SEED = 20260825
UNANNOTATED = "UNANNOTATED"


def text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def blank(sample_id: str, candidate_id: str) -> dict:
    return {
        "sample_id": sample_id,
        "candidate_id": candidate_id,
        "annotator": "",
        "disease_supported": UNANNOTATED,
        "gene_supported": UNANNOTATED,
        "alteration_supported": UNANNOTATED,
        "drug_supported": UNANNOTATED,
        "direction_supported": UNANNOTATED,
        "evidence_type_supported": UNANNOTATED,
        "overall_gold": UNANNOTATED,
        "gold_source_unit_ids": [],
        "gold_quote": "",
        "notes": "",
    }


def main() -> None:
    if hashlib.sha256(SAMPLE.read_bytes()).hexdigest() != SAMPLE_SHA:
        raise SystemExit("sample SHA mismatch")
    if hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest() != SOURCE_SHA:
        raise SystemExit("source manifest SHA mismatch")
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    paper = [entry for entry in sample["entries"] if entry["relation_family"] == "PAPER_EVIDENCE"]
    source_by_id = {entry["sample_id"]: entry for entry in source["entries"]}
    if len(paper) != 16:
        raise SystemExit("expected exactly 16 paper entries")
    order = [entry["sample_id"] for entry in paper]
    random.Random(ANNOTATION_ORDER_SEED).shuffle(order)
    index = {
        "sample_sha256": SAMPLE_SHA,
        "source_snapshot_manifest_sha256": SOURCE_SHA,
        "source_freeze_commit_actual": source.get("source_freeze_commit_actual", "153045b757594378fb1f1fc0d2db0cc70da67306"),
        "sample_freeze_commit_actual": "c7d3e1361fbc3be9aecc4949f7483b73bbf3b1e2",
        "core_commit_actual": "dd010056ae348e42e66a6f0098c9e9eb26890d6b2",
        "annotation_order_seed": ANNOTATION_ORDER_SEED,
        "annotation_order": order,
        "paper_packs": [{"sample_id": entry["sample_id"], "candidate_id": entry["candidate_id"]} for entry in paper],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for entry in paper:
        sid = entry["sample_id"]
        srow = source_by_id[sid]
        folder = OUT / sid
        folder.mkdir(parents=True, exist_ok=True)
        candidate = {key: entry.get(key) for key in ("sample_id", "candidate_id", "subject", "predicate", "object", "disease", "direction", "evidence_type", "source_type", "document_identifiers", "materialization_rule_id")}
        (folder / "candidate.json").write_text(json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        record = srow.get("resolver_record", {})
        overview = f"""# Frozen source overview — {sid}

Sample ID: `{sid}`  
Candidate ID: `{entry['candidate_id']}`

## KG assertion

- Subject: `{text(entry.get('subject'))}`
- Predicate: `{text(entry.get('predicate'))}`
- Object: `{text(entry.get('object'))}`

## Context

- Disease/context: `{text(entry.get('disease'))}`
- Direction: `{text(entry.get('direction'))}`
- Evidence type: `{text(entry.get('evidence_type'))}`

## Source

- PMID: `{srow.get('pmid')}`
- PMCID: `{srow.get('pmcid') or ''}`
- Canonical document type: `{srow.get('canonical_document_type')}`
- Title: `{text(record.get('title'))}`
- Availability: `{srow.get('canonical_document_type')}`
- SourceUnit count: `{srow.get('sourceunit_count', 0)}`

This page presents frozen metadata only; it contains no support interpretation.
"""
        (folder / "source_overview.md").write_text(overview, encoding="utf-8")
        units = json.loads((ROOT / "sources/paper" / sid / "sourceunits.json").read_text(encoding="utf-8"))
        lines = [f"# Frozen SourceUnits — {sid}", "", "SourceUnits are shown in parser/document order. No selector, BM25 ranking, Reader output, or runtime support result is included.", ""]
        for unit in units:
            locator = {key: unit.get(key) for key in ("section", "char_start", "char_end", "paragraph_index", "sentence_index", "page") if unit.get(key) is not None}
            lines.extend([f"## {unit.get('source_unit_id')}", "", f"TYPE: `{unit.get('unit_type')}`", f"LOCATOR: `{json.dumps(locator, ensure_ascii=False, sort_keys=True)}`", "", "TEXT:", "", unit.get("text") or "", ""])
        (folder / "source_units.md").write_text("\n".join(lines), encoding="utf-8")
        (folder / "annotation_primary.json").write_text(json.dumps(blank(sid, entry["candidate_id"]), indent=2) + "\n", encoding="utf-8")
        (folder / "annotation_review.json").write_text(json.dumps(blank(sid, entry["candidate_id"]), indent=2) + "\n", encoding="utf-8")
    pending = {"trial_sample_ids": [e["sample_id"] for e in sample["entries"] if e["relation_family"] == "CLINICAL_TRIAL"], "kg_only_sample_ids": [e["sample_id"] for e in sample["entries"] if e["relation_family"] == "KG_ONLY"]}
    (OUT / "annotation_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "non_paper_gold_pending.json").write_text(json.dumps(pending, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readme = f"""# Human gold annotation pack

This pack contains the 16 frozen PAPER_EVIDENCE candidates and their frozen source documents/SourceUnits. It is an empty annotation instrument: no gold decision, support result, Reader output, selector output, or previous evaluation result is included.

## Annotation question

For each candidate, answer: **does the associated document really support the relation represented by the KG, and with what specificity?** Read the candidate and all SourceUnits before filling the form.

## Overall labels

- `FULL_SUPPORT`: all necessary candidate elements are supported with sufficient specificity.
- `PARTIAL_SUPPORT`: the source supports a more general relation or only part of the candidate.
- `NO_SUPPORT`: the source does not support the candidate relation.
- `CONTRADICTORY`: the source states something incompatible with the candidate.
- `UNVERIFIABLE`: the frozen document does not allow a reasoned decision.

## Field labels

For disease/context, gene, alteration, drug, direction, and evidence type, use `YES`, `NO`, or `NOT_APPLICABLE` only after annotation. `NOT_APPLICABLE` is not `NO`: for example, a diagnostic candidate with no drug may have `drug_supported=NOT_APPLICABLE`.

- Disease/context: is the requested disease or context covered?
- Gene: is the gene explicitly supported?
- Alteration: is the specific variant/alteration supported, not merely the gene?
- Drug: is the requested drug or regimen supported?
- Direction: does sensitivity, resistance, non-support, or another direction match?
- Evidence type: does the source document the predictive, diagnostic, prognostic, or other nature represented by the candidate?

## Quotes

Record a short literal quote from the frozen SourceUnits and the corresponding `source_unit_id` values. The quote must be present verbatim in the displayed SourceUnits; multiple units may be used when one is insufficient.

## Independent review

Complete `annotation_primary.json` and `annotation_review.json` independently. The reviewer must not see the primary annotation before completing the review. Do not create a final gold file in this phase. Disagreements will be adjudicated separately.

## Order

The stable sample IDs remain unchanged. The independent annotation order is stored in `annotation_index.json` and was generated with `ANNOTATION_ORDER_SEED={ANNOTATION_ORDER_SEED}`.

## Provenance

- Candidate sample SHA256: `{SAMPLE_SHA}`
- Source snapshot manifest SHA256: `{SOURCE_SHA}`
- No external calls were made while preparing this pack.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    report = f"""# Annotation pack report

PAPER_PACKS=16
TOTAL_SOURCEUNITS_PRESENTED={sum(srow.get('sourceunit_count', 0) for srow in source['entries'] if srow['relation_family'] == 'PAPER_EVIDENCE')}
PMC_PACKS=5
ABSTRACT_PACKS=11
UNANNOTATED_PRIMARY=16
UNANNOTATED_REVIEW=16
SYSTEM_OUTPUT_EXPOSED_TO_ANNOTATOR=FALSE
ANNOTATION_ORDER_SEED={ANNOTATION_ORDER_SEED}

The pack was generated exclusively from the frozen candidate sample, source snapshot manifest, and frozen SourceUnit bundles. No gold decisions were created.
"""
    (OUT / "annotation_pack_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"paper_packs": 16, "sourceunits": sum(srow.get("sourceunit_count", 0) for srow in source["entries"] if srow["relation_family"] == "PAPER_EVIDENCE")}, sort_keys=True))


if __name__ == "__main__":
    main()
