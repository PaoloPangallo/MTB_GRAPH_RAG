"""Congela il perimetro della revisione clinico/preclinica.

Le fonti sono quelle che l'audit strutturale ha classificato
`clinical_preclinical_split_required`. Il perimetro e' definito dal **criterio**,
non da un conteggio: il controllo confronta l'insieme derivato dagli artefatti
dell'audit con quello dichiarato e fallisce su qualunque divergenza.

Gli hash dei 35 packet della seconda revisione sono registrati **prima** che la
fase cominci. Serviranno a dimostrare, e non soltanto ad affermare, che nessuna
informazione emersa leggendo le fonti e' finita nei packet ciechi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import PROFILE_UNIT_VERSION  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    EXPECTED_SOURCES,
    REVIEW_VERSION,
    TARGET_STRUCTURE_STATE,
    check_scope,
    derive_scope,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_source_inventory import (  # noqa: E402
    write_csv,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

SECOND_REVIEW_DIR = Path("annotation_packets/second_review")
AUDIT_PACKET_DIR = Path("annotation_packets/first_review_split_audit")
FIRST_REVIEW_DIR = Path("annotation_packets/first_review")

COLUMNS = (
    "profile_unit_id",
    "canonical_source_id",
    "pmids",
    "dois",
    "ncts",
    "first_review_packet",
    "audit_packet",
    "second_review_packet",
    "statement_count",
    "statement_ids",
    "diseases",
    "biomarkers",
    "interventions",
    "directions",
    "assertion_polarities",
    "audit_signal_count",
    "audit_proposed_unit_ids",
    "source_availability",
    "full_text_available",
    "pmc_id",
    "source_hash",
    "known_conflict_count",
    "propagation_risk",
    "risk_band",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def hash_directory(directory: Path) -> dict[str, str]:
    """Hash di ogni file, per nome. L'ordine e' quello dei nomi, non del disco."""
    if not directory.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def build_rows(
    derived: Sequence[str],
    *,
    audit_dir: Path,
) -> list[dict[str, Any]]:
    scope = {str(row["profile_unit_id"]): row for row in read_jsonl(audit_dir / "audit_scope.jsonl")}
    access = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(audit_dir / "source_access_audit.jsonl")
    }
    proposals = {
        str(row["parent_profile_unit_id"]): row
        for row in read_jsonl(audit_dir / "split_proposals.jsonl")
    }
    signals = {
        str(row["profile_unit_id"]): row for row in read_jsonl(audit_dir / "detector_signals.jsonl")
    }
    classification = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(audit_dir / "source_structure_classification.jsonl")
    }

    rows: list[dict[str, Any]] = []
    for unit_id in derived:
        unit = scope.get(unit_id, {})
        source = access.get(unit_id, {})
        proposal = proposals.get(unit_id, {})
        signal = signals.get(unit_id, {})
        packet = str(unit.get("first_review_packet") or "")
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": unit.get("canonical_source_id", ""),
                "pmids": list(unit.get("pmids") or ()),
                "dois": list(unit.get("dois") or ()),
                "ncts": list(unit.get("ncts") or ()),
                "first_review_packet": packet,
                "audit_packet": packet,
                "second_review_packet": unit.get("second_review_packet", ""),
                "statement_ids": list(unit.get("statement_ids") or ()),
                "statement_count": int(unit.get("statement_count") or 0),
                "diseases": list(unit.get("diseases") or ()),
                "biomarkers": list(unit.get("biomarkers") or ()),
                "interventions": list(unit.get("interventions") or ()),
                "directions": list(unit.get("directions") or ()),
                "assertion_polarities": list(unit.get("assertion_polarities") or ()),
                "audit_structure_state": classification.get(unit_id, {}).get("structure_state", ""),
                "audit_signal_count": len(signal.get("signals") or ()),
                "audit_signal_categories": list(signal.get("categories") or ()),
                "audit_split_likelihood": signal.get("split_likelihood", ""),
                "audit_proposed_unit_ids": list(proposal.get("proposed_profile_unit_ids") or ()),
                "audit_proposal_count": int(proposal.get("proposal_count") or 0),
                "source_availability": source.get("availability", ""),
                "full_text_available": source.get("availability") == "full_text",
                "pmc_id": source.get("pmc_id", ""),
                "source_hash": source.get("source_hash", ""),
                "abstract_sha256": unit.get("abstract_sha256", ""),
                "known_conflict_count": int(unit.get("known_conflict_count") or 0),
                "propagation_risk": int(unit.get("propagation_risk") or 0),
                "risk_band": unit.get("risk_band", ""),
                "inclusion_reason": (
                    f"classificata {TARGET_STRUCTURE_STATE} dall'audit strutturale"
                ),
                "review_version": REVIEW_VERSION,
            }
        )
    return rows


def build_report(rows: Sequence[dict[str, Any]], digest: str) -> str:
    lines = [
        "# Perimetro della revisione clinico/preclinica",
        "",
        f"- **Hash del perimetro:** `{digest}`",
        f"- **Fonti nel batch:** {len(rows)}",
        "",
        "## Perche' queste tre",
        "",
        "L'audit strutturale ha letto i segnali delle nove fonti residue e ne ha",
        "classificate tre `clinical_preclinical_split_required`: contengono sia una",
        "componente clinica sia una preclinica, e un profilo unico le fonderebbe.",
        "",
        "L'audit si e' fermato li'. Un segnale dice **che** le due componenti esistono,",
        "non **quali** statement appartengano all'una e quali all'altra: tutti e sette",
        "gli statement di queste fonti sono rimasti `candidate_ambiguous`. Questa fase",
        "legge le fonti primarie per scioglierlo.",
        "",
        "## Fonti",
        "",
        "| Unita' | PMID | Statement | Full text | Segnali | Rischio |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in rows:
        full_text = f"`{row['pmc_id']}`" if row["full_text_available"] else "**assente**"
        lines.append(
            f"| `{row['profile_unit_id']}` | {', '.join(row['pmids']) or '—'} | "
            f"{row['statement_count']} | {full_text} | {row['audit_signal_count']} | "
            f"{row['risk_band']} ({row['propagation_risk']}) |"
        )

    without_full_text = [row for row in rows if not row["full_text_available"]]
    lines += [
        "",
        "## Disponibilita' documentale",
        "",
        f"- Con full text pubblico: **{len(rows) - len(without_full_text)}** su {len(rows)}",
        f"- Solo abstract: **{len(without_full_text)}**",
        "",
    ]
    if without_full_text:
        names = ", ".join(f"`{row['profile_unit_id']}`" for row in without_full_text)
        lines += [
            f"Per {names} il full text non e' in PMC. La verifica documentale si ferma",
            "a cio' che l'abstract espone, e la decisione strutturale deve dirlo invece",
            "di concludere lo split su una base che non lo sostiene.",
            "",
        ]
    lines += [
        "## Che cosa questa fase non fa",
        "",
        "Non produce revisioni umane. Il tetto assegnabile e'",
        "`source_checked_review_proposal`, con `human_reviewed = false` e",
        "`requires_author_approval = true`: le proposte vanno approvate dall'autore",
        "prima di poter diventare gold, e restano non propagabili fino ad allora.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    classifications = list(read_jsonl(args.audit_dir / "source_structure_classification.jsonl"))
    derived = derive_scope(classifications)
    check_scope(derived)

    rows = build_rows(derived, audit_dir=args.audit_dir)
    digest = content_hash(rows)

    corpus = json.loads(
        (args.corpus_dir / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
    )
    second_review_hashes = hash_directory(args.curation_dir / SECOND_REVIEW_DIR)

    write_jsonl(output / "review_batch_scope.jsonl", rows)
    write_csv(output / "review_batch_scope.csv", rows, COLUMNS)
    write_json(
        output / "review_batch_scope.json",
        {
            "review_version": REVIEW_VERSION,
            "created_at": created_at,
            "criterion": f"structure_state == {TARGET_STRUCTURE_STATE}",
            "expected_sources": list(EXPECTED_SOURCES),
            "derived_sources": derived,
            "source_count": len(rows),
            "review_batch_scope_hash": digest,
            "clinical_gold_used": False,
            "sources": rows,
        },
    )
    write_json(
        output / "review_batch_manifest.json",
        {
            "review_version": REVIEW_VERSION,
            "created_at": created_at,
            "review_batch_scope_hash": digest,
            "statement_repository_hash": corpus["statement_repository_hash"],
            "source_inventory_hash": corpus["source_inventory_hash"],
            "snapshot_fingerprint": corpus["snapshot_fingerprint"],
            "schema_versions": {
                "clinical_preclinical_review": REVIEW_VERSION,
                "source_clinical_profile_unit": PROFILE_UNIT_VERSION,
            },
            "source_count": len(rows),
            "second_review_packet_count": len(second_review_hashes),
            "second_review_hashes_before": second_review_hashes,
            "clinical_gold_used": False,
            "batch_status": "scope_frozen",
        },
    )
    write_text(output / "REVIEW_BATCH_SCOPE.md", build_report(rows, digest))

    print(f"fonti nel batch: {len(rows)}")
    print(f"review_batch_scope_hash: {digest}")
    print(f"packet di seconda revisione registrati: {len(second_review_hashes)}")
    for row in rows:
        state = "full text" if row["full_text_available"] else "solo abstract"
        print(f"  {row['profile_unit_id']}: {row['statement_count']} statement, {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
