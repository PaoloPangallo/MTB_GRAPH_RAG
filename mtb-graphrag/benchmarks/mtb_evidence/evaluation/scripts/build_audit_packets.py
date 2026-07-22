"""Packet di prima revisione aggiornati con la struttura proposta dall'audit.

Gli originali non vengono toccati: questi vivono in una cartella separata e
citano il packet da cui derivano. Un revisore che apra la versione aggiornata
deve poter risalire a quella precedente.

I packet della seconda revisione non vengono ne' letti per contenuto ne'
scritti. Il loro hash viene calcolato prima e dopo, e confrontato: e' l'unico
modo per dimostrare che l'audit non li ha toccati, invece di affermarlo.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.cohort_split_audit import (  # noqa: E402
    AUDIT_VERSION,
    SPLIT_PROPOSED_BY_AUDIT,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _hash_dir(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.glob("*"))
        if item.is_file()
    }


def build_packet(
    *,
    scope: Mapping[str, Any],
    classification: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
    mappings: Sequence[Mapping[str, Any]],
    signals: Mapping[str, Any],
    access: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "blind_annotation_id": scope["first_review_packet"],
        "packet_version": "first_review_split_audit/1.0",
        "supersedes_packet": scope["first_review_packet"],
        "audit_state": SPLIT_PROPOSED_BY_AUDIT,
        "source": {
            "pmids": list(scope.get("pmids") or ()),
            "canonical_source_id": scope["canonical_source_id"],
            "locator": access.get("exact_locator", ""),
            "text_consulted": access.get("availability", ""),
            "document_hash": access.get("document_hash", ""),
            "limitations": access.get("limitations", ""),
        },
        "proposed_structure": {
            "structure_state": classification["structure_state"],
            "rationale": classification["structure_rationale"],
            "split_likelihood": classification["split_likelihood"],
            "documentary_units": classification["documentary_units"],
            "arms_detected": classification["arms_detected"],
            "preclinical_models_detected": classification["preclinical_models_detected"],
            "comparators_detected": classification["comparators_detected"],
        },
        "candidate_units": [
            {
                "proposed_profile_unit_id": item["proposed_profile_unit_id"],
                "unit_type": item["unit_type"],
                "unit_label": item["unit_label"],
                "evidence_design": item["evidence_design"],
                "is_propagatable": item["is_propagatable"],
                "review_status": item["review_status"],
            }
            for item in proposals
        ],
        "statements": [
            {
                "statement_id": item["statement_id"],
                "intervention": item["intervention"],
                "candidate_link_status": item["candidate_link_status"],
                "support_type": item["support_type"],
                "clinical_or_preclinical": item["clinical_or_preclinical"],
                "rationale": item["rationale"],
            }
            for item in mappings
        ],
        "shared_dimensions": list(classification["shared_dimensions"]),
        "specific_dimensions": list(classification["specific_dimensions"]),
        "not_separable_dimensions": list(classification["not_separable_dimensions"]),
        "non_propagation_warnings": [
            f"non propagare `{dimension}` fra componente clinica e preclinica"
            for dimension in classification["do_not_propagate"]
        ],
        "detected_signals": [
            {
                "signal_id": item["signal_id"],
                "category": item["category"],
                "matched_text": item["matched_text"],
            }
            for item in (signals.get("signals") or [])[:12]
        ],
        "source_excerpts": list(signals.get("excerpts") or [])[:8],
        "reviewer_questions": [
            "La fonte descrive davvero le unita' proposte, o la partizione e' un artefatto "
            "dei segnali lessicali?",
            "Quali proposizioni appartengono a ciascuna unita'?",
            "Quali dimensioni sono condivise fra le unita' e quali sono specifiche?",
            "Esistono dimensioni che la fonte non permette di separare? Marcale "
            "`not_separable`, non `unknown`.",
            "La proposta va accettata, modificata o respinta?",
        ],
        "instructions": [
            "Questa e' una **proposta strutturale automatica**, non una revisione.",
            "I campi clinici delle unita' proposte sono deliberatamente vuoti: l'audit "
            "propone struttura, non contenuto.",
            "Respingere la proposta e' un esito legittimo quanto accettarla.",
        ],
        "contains_clinical_gold": False,
        "contains_expected_therapy": False,
        "contains_pipeline_metrics": False,
        "contains_final_decision": False,
        "contains_other_reviewer_decision": False,
        "contains_reviewed_packet_outcome": False,
        "audit_version": AUDIT_VERSION,
    }


def render_markdown(packet: Mapping[str, Any]) -> str:
    structure = packet["proposed_structure"]
    source = packet["source"]
    lines = [
        f"# Proposta strutturale — {packet['blind_annotation_id']}",
        "",
        "> Questa e' una **proposta automatica**, non una revisione. Respingerla e' un",
        "> esito legittimo quanto accettarla.",
        "",
        "## Fonte",
        "",
        f"- **PMID:** {', '.join(source.get('pmids') or []) or '—'}",
        f"- **Testo consultato:** {source.get('text_consulted') or '—'}",
        f"- **Locator:** {source.get('locator') or '—'}",
    ]
    if source.get("limitations"):
        lines.append(f"- **Limiti:** {source['limitations']}")

    lines += [
        "",
        "## Struttura proposta",
        "",
        f"- **Stato:** `{structure['structure_state']}`",
        f"- **Verdetto del rilevatore:** `{structure['split_likelihood']}`",
        f"- Bracci rilevati: {structure['arms_detected']} · modelli preclinici: "
        f"{structure['preclinical_models_detected']} · comparatori: "
        f"{structure['comparators_detected']}",
        "",
        structure["rationale"] + ".",
        "",
    ]

    if packet["candidate_units"]:
        lines += ["## Unita' candidate", "", "| Unita' | Tipo | Propagabile |", "| --- | --- | --- |"]
        for item in packet["candidate_units"]:
            lines.append(
                f"| `{item['proposed_profile_unit_id']}` | `{item['unit_type']}` | "
                f"{'sì' if item['is_propagatable'] else '**no**'} |"
            )
        lines.append("")
    else:
        lines += [
            "## Unita' candidate",
            "",
            "Nessuna. I segnali indicano molteplicita' ma non permettono di delimitare le",
            "unita': proporne di numerate creerebbe partizioni che la fonte non afferma.",
            "",
        ]

    lines += ["## Proposizioni", "", "| statement | intervento | candidato | supporto |", "| --- | --- | --- | --- |"]
    for item in packet["statements"]:
        lines.append(
            f"| `{item['statement_id']}` | {item['intervention'] or '—'} | "
            f"`{item['candidate_link_status']}` | `{item['support_type']}` |"
        )

    if packet["non_propagation_warnings"]:
        lines += ["", "## Da non propagare", ""]
        lines += [f"- {item}" for item in packet["non_propagation_warnings"]]

    if packet["source_excerpts"]:
        lines += ["", "## Estratti", ""]
        for item in packet["source_excerpts"]:
            lines.append(f"- **{item.get('signal_id')}** — «{item.get('excerpt')}»")

    lines += ["", "## Domande al revisore", ""]
    lines += [f"{i}. {q}" for i, q in enumerate(packet["reviewer_questions"], start=1)]
    lines += [
        "",
        "---",
        "",
        "Questo pacchetto non contiene clinical gold, terapie attese, metriche della",
        "pipeline, decisioni finali ne' l'esito del pacchetto gia' revisionato.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audit = args.audit_dir
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    second_dir = args.curation_dir / "annotation_packets/second_review"
    before = _hash_dir(second_dir)

    scope = {str(row["profile_unit_id"]): row for row in read_jsonl(audit / "audit_scope.jsonl")}
    classifications = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(audit / "source_structure_classification.jsonl")
    }
    access = {
        str(row["profile_unit_id"]): row for row in read_jsonl(audit / "source_access_audit.jsonl")
    }
    signals = {
        str(row["profile_unit_id"]): row for row in read_jsonl(audit / "detector_signals.jsonl")
    }
    proposals_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl(audit / "proposed_profile_units.jsonl"):
        proposals_by_parent.setdefault(str(row["parent_profile_unit_id"]), []).append(row)
    mappings_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl(audit / "statement_unit_mapping_proposals.jsonl"):
        mappings_by_parent.setdefault(str(row["parent_profile_unit_id"]), []).append(row)

    target = audit / "annotation_packets/first_review_split_audit"
    written = 0
    for unit_id, row in sorted(scope.items()):
        packet = build_packet(
            scope=row,
            classification=classifications[unit_id],
            proposals=sorted(
                proposals_by_parent.get(unit_id, []),
                key=lambda item: item["proposed_profile_unit_id"],
            ),
            mappings=sorted(
                mappings_by_parent.get(unit_id, []), key=lambda item: item["statement_id"]
            ),
            signals=signals.get(unit_id, {}),
            access=access.get(unit_id, {}),
        )
        blind = str(row["first_review_packet"])
        write_json(target / f"{blind}.json", packet)
        write_text(target / f"{blind}.md", render_markdown(packet))
        written += 1

    after = _hash_dir(second_dir)
    unchanged = before == after
    write_json(
        audit / "second_review_blinding_check.json",
        {
            "created_at": created_at,
            "directory": str(second_dir).replace("\\", "/"),
            "file_count_before": len(before),
            "file_count_after": len(after),
            "hashes_before": before,
            "hashes_after": after,
            "byte_identical": unchanged,
            "changed_files": sorted(
                name for name in set(before) | set(after) if before.get(name) != after.get(name)
            ),
            "note": (
                "l'invarianza e' dimostrata confrontando gli hash prima e dopo, non "
                "affermata: l'audit non apre questi file in scrittura"
            ),
        },
    )

    print(f"packet aggiornati: {written}")
    print(f"packet di seconda revisione invariati byte per byte: {unchanged}")
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
