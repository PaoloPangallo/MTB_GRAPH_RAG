"""Congela il perimetro dell'audit strutturale delle coorti.

Il perimetro e' definito dal **criterio**, non da un conteggio atteso: le unita'
che la priority curation aveva lasciato in `cohort_partially_resolved`, meno
quella gia' revisionata e sostituita.

Una nota che conta per chi legge i numeri. La specifica di questa fase
prevedeva 8 unita' residue, assumendo che PMID 22277784 fosse fra le
`cohort_partially_resolved` e andasse sottratta. Non lo era: quella fonte era
classificata `insufficient_source_information`, cioe' nel bucket **piu' debole**,
pur avendo dieci statement. Le unita' residue sono quindi 9, e il fatto e' piu'
importante della differenza di conteggio — dice che il rilevatore non ha mancato
PMID 22277784 per poco, ma non l'ha segnalata affatto.

Il controllo di perimetro verifica l'insieme derivato programmaticamente contro
quello dichiarato, e fallisce su qualunque divergenza. Forzarlo a 8 avrebbe
richiesto di escludere una unita' senza motivo.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from benchmarks.mtb_evidence.evaluation.cohort_split_audit import AUDIT_VERSION  # noqa: E402
from benchmarks.mtb_evidence.evaluation.scripts.build_source_inventory import (  # noqa: E402
    write_csv,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")

TARGET_STATE = "cohort_partially_resolved"
ALREADY_REVIEWED = "PU-PMID-22277784-cohort-1"

# Insieme atteso, dichiarato esplicitamente perche' il controllo possa
# confrontarlo con quello derivato invece di fidarsi di un conteggio.
EXPECTED_UNITS = (
    "PU-PMID-22235099-cohort-1",
    "PU-PMID-22285168-cohort-1",
    "PU-PMID-23344087-cohort-1",
    "PU-PMID-27130468-cohort-1",
    "PU-PMID-27870574-cohort-1",
    "PU-PMID-27959700-cohort-1",
    "PU-PMID-28958502-cohort-1",
    "PU-PMID-31358542-cohort-1",
    "PU-PMID-32203698-cohort-1",
)

COLUMNS = (
    "profile_unit_id",
    "canonical_source_id",
    "pmids",
    "dois",
    "ncts",
    "first_review_packet",
    "second_review_packet",
    "statement_count",
    "statement_ids",
    "diseases",
    "biomarkers",
    "interventions",
    "directions",
    "assertion_polarities",
    "previous_cohort_state",
    "abstract_available",
    "full_text_available",
    "abstract_sha256",
    "known_conflict_count",
    "propagation_risk",
    "risk_band",
    "inclusion_reason",
)


class ScopeMismatch(RuntimeError):
    """Il perimetro derivato non coincide con quello dichiarato."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def derive_scope(resolutions: Sequence[dict[str, Any]]) -> list[str]:
    """Le unita' del perimetro, derivate dal criterio e non dal conteggio."""
    return sorted(
        str(row["profile_unit_id"])
        for row in resolutions
        if row.get("resolution_state") == TARGET_STATE
        and str(row["profile_unit_id"]) != ALREADY_REVIEWED
    )


def check_scope(derived: Sequence[str]) -> None:
    """Fallisce su qualunque divergenza dall'insieme dichiarato."""
    derived_set = set(derived)
    expected_set = set(EXPECTED_UNITS)
    if ALREADY_REVIEWED in derived_set:
        raise ScopeMismatch(
            f"{ALREADY_REVIEWED} e' nel perimetro: e' gia' stata revisionata e sostituita"
        )
    missing = expected_set - derived_set
    extra = derived_set - expected_set
    if missing or extra:
        raise ScopeMismatch(
            f"perimetro divergente. Mancanti: {sorted(missing)}. In piu': {sorted(extra)}. "
            "Il perimetro segue il criterio, non un conteggio: aggiornare EXPECTED_UNITS "
            "solo dopo aver capito perche' l'insieme e' cambiato."
        )


def build_report(rows: Sequence[dict[str, Any]], digest: str) -> str:
    lines = [
        "# Perimetro dell'audit strutturale",
        "",
        f"- **Hash del perimetro:** `{digest}`",
        f"- **Unita' residue:** {len(rows)}",
        "",
        "## Perche' sono nove e non otto",
        "",
        "La specifica prevedeva otto unita' residue, assumendo che PMID 22277784 fosse",
        "fra le `cohort_partially_resolved` e andasse sottratta. Non lo era: quella",
        "fonte era classificata **`insufficient_source_information`**, cioe' nel bucket",
        "piu' debole, pur avendo dieci statement.",
        "",
        "La differenza di conteggio e' il dettaglio meno interessante. Il fatto e' che",
        "la fonte di cui oggi sappiamo con certezza che contiene una coorte clinica e",
        "tre pannelli su cellule non era stata segnalata **affatto** — non e' stata",
        "mancata per poco. Il segnale che avrebbe dovuto accenderla vive nel full text,",
        "e il rilevatore leggeva solo l'abstract e la distribuzione degli statement.",
        "",
        "Il perimetro segue quindi il criterio della specifica — le unita'",
        "`cohort_partially_resolved` meno quella gia' revisionata — e il controllo",
        "confronta l'insieme derivato con quello dichiarato invece di fidarsi di un",
        "numero.",
        "",
        "## Unita' nel perimetro",
        "",
        "| Unita' | Statement | Interventi | Rischio |",
        "| --- | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['profile_unit_id']}` | {row['statement_count']} | "
            f"{', '.join(row['interventions']) or '—'} | "
            f"{row['risk_band']} ({row['propagation_risk']}) |"
        )
    lines += [
        "",
        "## Disponibilita' delle fonti",
        "",
        f"- Con abstract: {sum(1 for row in rows if row['abstract_available'])}",
        f"- Con full text pubblico: {sum(1 for row in rows if row['full_text_available'])}",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    resolutions = list(read_jsonl(args.curation_dir / "cohort_resolution_decisions.jsonl"))
    derived = derive_scope(resolutions)
    check_scope(derived)

    priority = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.curation_dir / "priority_units.jsonl")
    }
    access = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.curation_dir / "source_access_manifest.jsonl")
    }
    mapping = json.loads(
        (args.curation_dir / "blind_id_mapping.json").read_text(encoding="utf-8")
    )
    blind = {str(row["profile_unit_id"]): row for row in mapping["mapping"]}
    resolution_by_id = {str(row["profile_unit_id"]): row for row in resolutions}

    rows: list[dict[str, Any]] = []
    for unit_id in derived:
        unit = priority.get(unit_id, {})
        source = access.get(unit_id, {})
        ids = blind.get(unit_id, {})
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": unit.get("canonical_source_id", ""),
                "pmids": list(unit.get("pmids") or ()),
                "dois": list(unit.get("dois") or ()),
                "ncts": list(unit.get("ncts") or ()),
                "first_review_packet": ids.get("first_review_blind_id", ""),
                "second_review_packet": ids.get("second_review_blind_id", ""),
                "statement_ids": list(unit.get("statement_ids") or ()),
                "statement_count": int(unit.get("statement_count") or 0),
                "diseases": list(unit.get("diseases") or ()),
                "biomarkers": list(unit.get("biomarkers") or ()),
                "interventions": list(unit.get("interventions") or ()),
                "directions": list(unit.get("directions") or ()),
                "assertion_polarities": list(unit.get("assertion_polarities") or ()),
                "previous_cohort_state": resolution_by_id.get(unit_id, {}).get(
                    "resolution_state", ""
                ),
                "abstract_available": bool(source.get("abstract_available")),
                "full_text_available": False,
                "abstract_sha256": source.get("abstract_sha256", ""),
                "known_conflict_count": len(unit.get("known_conflicts") or ()),
                "propagation_risk": int(unit.get("propagation_risk") or 0),
                "risk_band": unit.get("risk_band", ""),
                "inclusion_reason": (
                    "classificata cohort_partially_resolved dalla priority curation e "
                    "mai revisionata"
                ),
                "audit_version": AUDIT_VERSION,
            }
        )

    digest = content_hash(rows)
    previous = json.loads(
        (args.corpus_dir / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
    )

    write_jsonl(output / "audit_scope.jsonl", rows)
    write_csv(output / "audit_scope.csv", rows, COLUMNS)
    write_json(
        output / "audit_scope.json",
        {
            "audit_version": AUDIT_VERSION,
            "created_at": created_at,
            "criterion": f"resolution_state == {TARGET_STATE}",
            "excluded_unit": ALREADY_REVIEWED,
            "exclusion_reason": "gia' revisionata e sostituita da quattro unita' derivate",
            "expected_units": list(EXPECTED_UNITS),
            "derived_units": derived,
            "unit_count": len(rows),
            "specification_expected_count": 8,
            "specification_discrepancy": (
                "la specifica prevedeva 8 unita' assumendo che PMID 22277784 fosse fra le "
                "cohort_partially_resolved. Era invece insufficient_source_information, "
                "quindi le residue sono 9. Il perimetro segue il criterio, non il conteggio."
            ),
            "audit_scope_hash": digest,
            "units": rows,
        },
    )
    write_json(
        output / "audit_scope_manifest.json",
        {
            "audit_version": AUDIT_VERSION,
            "created_at": created_at,
            "audit_scope_hash": digest,
            "statement_repository_hash": previous["statement_repository_hash"],
            "source_inventory_hash": previous["source_inventory_hash"],
            "qualification_scope_hash": previous["qualification_scope_hash"],
            "snapshot_fingerprint": previous["snapshot_fingerprint"],
            "unit_count": len(rows),
            "clinical_gold_used": False,
        },
    )
    write_text(output / "AUDIT_SCOPE_REPORT.md", build_report(rows, digest))

    print(f"unita' nel perimetro: {len(rows)}")
    print(f"audit_scope_hash: {digest}")
    print(f"{ALREADY_REVIEWED} escluso: {ALREADY_REVIEWED not in derived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
