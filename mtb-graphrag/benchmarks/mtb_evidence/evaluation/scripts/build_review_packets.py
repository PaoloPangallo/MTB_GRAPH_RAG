"""Costruisce i packet ciechi di prima e seconda revisione, e le loro code."""

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

from backend.pipeline.evidence.profile_unit import UNKNOWN  # noqa: E402
from backend.pipeline.evidence.qualification_gold import RATIONALE_CODES  # noqa: E402
from benchmarks.mtb_evidence.evaluation.scripts.build_source_inventory import (  # noqa: E402
    write_csv,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/priority_curation")

# Il salt rende l'id di seconda revisione non derivabile da quello di prima.
# Senza, un revisore che vedesse entrambe le code potrebbe allineare i due
# pacchetti e la seconda revisione smetterebbe di essere indipendente.
SECOND_REVIEW_SALT = "second-review/v1"

FIELDS_TO_CONFIRM = (
    ("disease", "Malattia studiata, con la denominazione della fonte."),
    ("histology", "Istologia, se la fonte la specifica."),
    ("population", "Popolazione arruolata."),
    ("stage", "Stadio di malattia."),
    ("setting", "Adiuvante, neoadiuvante, metastatico, perioperatorio, altro."),
    ("therapy_line", "Linea di terapia."),
    ("resection_status", "Stato di resezione."),
    ("intervention", "Interventi somministrati in questo braccio."),
    ("regimen", "Regime completo, incluse le combinazioni."),
    ("comparator", "Braccio di confronto, se esiste."),
    ("prior_therapies", "Terapie precedenti richieste o ammesse."),
    ("biomarker_requirements", "Alterazioni richieste per l'arruolamento."),
    ("inclusion_criteria", "Criteri di inclusione, in sintesi."),
    ("exclusion_criteria", "Criteri di esclusione, in sintesi."),
    ("study_design", "Disegno dello studio."),
    ("evidence_scope", "Ambito dell'evidenza."),
    ("cohort_notes", "Note sulla struttura delle coorti."),
)

INSTRUCTIONS = (
    "Leggi la fonte primaria. Non compilare nulla da memoria.",
    "Compila un campo solo se la fonte lo afferma. Se non lo afferma, lascia `unknown`.",
    "Se la fonte descrive piu' coorti e non sai a quale appartiene una proposizione, "
    "usa `not_separable`. Non sceglierne una.",
    "`unknown` e `not_separable` non sono la stessa cosa: il primo dice che non lo "
    "sappiamo, il secondo che la fonte non lo distingue.",
    "Per ogni campo compilato indica sezione o tabella da cui viene il valore.",
    "Le rilevazioni automatiche allegate sono proposte da verificare, non risposte. "
    "Alcune sono note per essere sbagliate.",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def second_blind_id(profile_unit_id: str) -> str:
    digest = hashlib.sha256(f"{SECOND_REVIEW_SALT}|{profile_unit_id}".encode("utf-8")).hexdigest()
    return f"BB-{digest[:16]}"


def build_packet(
    *,
    unit: Mapping[str, Any],
    priority: Mapping[str, Any],
    proposal: Mapping[str, Any],
    resolution: Mapping[str, Any],
    spans: Mapping[str, Any] | None,
    candidates: Sequence[Mapping[str, Any]],
    blind_id: str,
    round_name: str,
) -> dict[str, Any]:
    """Un packet cieco.

    I due round condividono esattamente gli stessi dati sorgente. La differenza
    e' solo l'identificatore: il packet di seconda revisione non contiene la
    decisione del primo revisore, altrimenti la seconda revisione misurerebbe
    quanto il secondo annotatore concorda con il primo dopo averlo letto.
    """
    return {
        "blind_annotation_id": blind_id,
        "review_round": round_name,
        "source": {
            "pmids": list(unit.get("pmids") or ()),
            "dois": list(unit.get("dois") or ()),
            "ncts": list(unit.get("ncts") or ()),
            "title": unit.get("title", ""),
            "locator": str(spans.get("locator") or "") if spans else "",
            "publication_types": list(spans.get("publication_types") or ()) if spans else [],
            "mesh_terms": list(spans.get("mesh_terms") or ()) if spans else [],
            "abstract_available": bool(spans and spans.get("abstract_available")),
            "abstract_sha256": str(spans.get("abstract_sha256") or "") if spans else "",
        },
        "cohort_question": {
            "automatic_state": resolution.get("resolution_state", ""),
            "explanation": resolution.get("explanation", ""),
            "multi_cohort_markers": [
                item.get("matched_text") for item in resolution.get("multi_cohort_markers") or []
            ],
            "single_cohort_markers": [
                item.get("matched_text") for item in resolution.get("single_cohort_markers") or []
            ],
            "comparator_present": bool(resolution.get("comparator_markers")),
            "question": (
                "Quante coorti descrive questa fonte? Se piu' di una, quali proposizioni "
                "appartengono a ciascuna? Se non e' determinabile, indica `not_separable`."
            ),
        },
        "candidate_statements": [
            {
                "statement_id": item["statement_id"],
                "intervention": item.get("intervention", ""),
                "automatic_classification": item.get("candidate_state", ""),
                "support_type": item.get("support_type", ""),
                "explanation": item.get("explanation", ""),
            }
            for item in candidates
        ],
        "automatic_extraction": {
            "emitted": proposal.get("proposed_dimensions", {}),
            "detected_not_emitted": proposal.get("review_questions", {}),
            "contradicted": proposal.get("contradicted_dimensions", []),
            "caveat": (
                "Le rilevazioni non emesse provengono da corrispondenze lessicali che "
                "possono descrivere i campioni invece dello studio. Vanno confermate "
                "sulla fonte."
            ),
        },
        "source_excerpts": [
            {
                "section_label": item.get("section_label"),
                "matched_text": item.get("matched_text"),
                "excerpt": item.get("excerpt"),
            }
            for item in (spans.get("span_excerpts") or [] if spans else [])
        ],
        "known_conflicts": list(priority.get("known_conflicts") or ()),
        "fields_to_confirm": [
            {"field": name, "guidance": guidance, "value": UNKNOWN, "source_locator": ""}
            for name, guidance in FIELDS_TO_CONFIRM
        ],
        "allowed_values": {
            "unknown": "la fonte non lo afferma",
            "not_separable": "la fonte non distingue fra le coorti",
            "link_status": [
                "valid_link",
                "partial_link",
                "ambiguous_link",
                "conflicting_link",
                "invalid_link",
                "no_profile_available",
                "source_missing",
                "insufficient_source_information",
            ],
            "rationale_codes": list(RATIONALE_CODES),
        },
        "instructions": list(INSTRUCTIONS),
        "contains_clinical_gold": False,
        "contains_expected_therapy": False,
        "contains_pipeline_metrics": False,
        "contains_audit_decision": False,
        "contains_first_review_decision": False,
        "contains_metric_impact": False,
    }


def render_markdown(packet: Mapping[str, Any]) -> str:
    source = packet["source"]
    cohort = packet["cohort_question"]
    lines = [
        f"# Revisione {packet['blind_annotation_id']} — {packet['review_round']}",
        "",
        "## Fonte",
        "",
        f"- **Titolo:** {source.get('title') or '(non disponibile)'}",
        f"- **PMID:** {', '.join(source.get('pmids') or []) or '—'}",
        f"- **Locator:** {source.get('locator') or '—'}",
        f"- **Tipi di pubblicazione:** {', '.join(source.get('publication_types') or []) or '—'}",
        f"- **Abstract disponibile:** {'sì' if source.get('abstract_available') else 'no'}",
        "",
        "## Domanda sulla struttura delle coorti",
        "",
        f"> {cohort['question']}",
        "",
        f"- Stato automatico: `{cohort['automatic_state']}`",
        f"- Marcatori di piu' bracci: {', '.join(cohort['multi_cohort_markers']) or '—'}",
        f"- Marcatori di braccio unico: {', '.join(cohort['single_cohort_markers']) or '—'}",
        f"- Comparatore rilevato: {'sì' if cohort['comparator_present'] else 'no'}",
        "",
        cohort["explanation"],
        "",
        "## Proposizioni candidate",
        "",
        "| statement | intervento | classificazione automatica | supporto |",
        "| --- | --- | --- | --- |",
    ]
    for item in packet["candidate_statements"]:
        lines.append(
            f"| `{item['statement_id']}` | {item['intervention']} | "
            f"`{item['automatic_classification']}` | `{item['support_type']}` |"
        )

    extraction = packet["automatic_extraction"]
    lines += ["", "## Rilevazioni automatiche", ""]
    if extraction["emitted"]:
        lines += ["**Emesse come valore:**", ""]
        for dimension, item in sorted(extraction["emitted"].items()):
            lines.append(f"- `{dimension}` = `{item['value']}` — «{item['matched_text']}» ({item['section_label']})")
        lines.append("")
    if extraction["detected_not_emitted"]:
        lines += ["**Rilevate ma NON emesse — da verificare sulla fonte:**", ""]
        for dimension, item in sorted(extraction["detected_not_emitted"].items()):
            lines.append(f"- `{dimension}` ⇒ `{item['value']}`? — «{item['matched_text']}» ({item['section_label']})")
        lines.append("")
    if extraction["contradicted"]:
        lines += [
            "**Rilevazioni discordanti, nessun valore proposto:** "
            + ", ".join(f"`{item}`" for item in extraction["contradicted"]),
            "",
        ]
    lines += [extraction["caveat"], ""]

    if packet["source_excerpts"]:
        lines += ["## Estratti", ""]
        for item in packet["source_excerpts"]:
            lines.append(f"- **{item['section_label']}** — «{item['excerpt']}»")
        lines.append("")

    if packet["known_conflicts"]:
        lines += ["## Conflitti gia' registrati", ""]
        for conflict in packet["known_conflicts"]:
            lines.append(
                f"- `{conflict.get('dimension')}`: fonte «{conflict.get('profile_value')}» "
                f"contro proposizione «{conflict.get('statement_value')}»"
            )
        lines.append("")

    lines += ["## Campi da confermare", "", "| campo | indicazione |", "| --- | --- |"]
    for item in packet["fields_to_confirm"]:
        lines.append(f"| `{item['field']}` | {item['guidance']} |")

    lines += ["", "## Istruzioni", ""]
    lines += [f"{index}. {text}" for index, text in enumerate(packet["instructions"], start=1)]
    lines += [
        "",
        "---",
        "",
        "Questo pacchetto non contiene il clinical gold, la terapia attesa, le metriche",
        "della pipeline, le decisioni dell'audit ne' l'indicazione di quale risposta",
        "migliori il sistema. Se fosse presente anche solo una di queste, la revisione",
        "non sarebbe indipendente.",
        "",
    ]
    return "\n".join(lines) + "\n"


QUEUE_COLUMNS = (
    "queue_position",
    "blind_annotation_id",
    "risk_band",
    "propagation_risk",
    "statement_count",
    "cohort_resolution_state",
    "abstract_available",
    "has_known_conflict",
    "estimated_effort",
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    priority = {str(row["profile_unit_id"]): row for row in read_jsonl(output / "priority_units.jsonl")}
    proposals = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(output / "curated_profile_proposals.jsonl")
    }
    resolutions = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(output / "cohort_resolution_decisions.jsonl")
    }
    spans = {
        str(row["identifier_key"]): row for row in read_jsonl(output / "source_abstract_spans.jsonl")
    }
    units = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(output / "resolved_profile_units.jsonl")
    }
    units.update(
        {
            str(row["profile_unit_id"]): row
            for row in read_jsonl(output / "unresolved_profile_units.jsonl")
        }
    )
    candidates_by_unit: dict[str, list[Mapping[str, Any]]] = {}
    for row in read_jsonl(output / "statement_profile_candidates.jsonl"):
        candidates_by_unit.setdefault(str(row["profile_unit_id"]), []).append(row)

    ordered = sorted(
        priority.values(),
        key=lambda item: (-int(item["propagation_risk"]), str(item["profile_unit_id"])),
    )

    mapping: list[dict[str, Any]] = []
    first_rows: list[dict[str, Any]] = []
    second_rows: list[dict[str, Any]] = []

    for position, item in enumerate(ordered, start=1):
        unit_id = str(item["profile_unit_id"])
        unit = units.get(unit_id, item)
        resolution = resolutions.get(unit_id, {})
        proposal = proposals.get(unit_id, {})
        span = None
        for pmid in item.get("pmids") or ():
            span = spans.get(f"pmid:{pmid}")
            if span:
                break

        first_id = str(item.get("blind_annotation_id") or unit_id)
        second_id = second_blind_id(unit_id)
        candidates = sorted(
            candidates_by_unit.get(unit_id, []), key=lambda row: row["statement_id"]
        )

        for blind, round_name, folder, rows in (
            (first_id, "first_review", "first_review", first_rows),
            (second_id, "second_review", "second_review", second_rows),
        ):
            packet = build_packet(
                unit=unit,
                priority=item,
                proposal=proposal,
                resolution=resolution,
                spans=span,
                candidates=candidates,
                blind_id=blind,
                round_name=round_name,
            )
            write_json(output / "annotation_packets" / folder / f"{blind}.json", packet)
            write_text(
                output / "annotation_packets" / folder / f"{blind}.md", render_markdown(packet)
            )
            rows.append(
                {
                    "queue_position": position,
                    "blind_annotation_id": blind,
                    "risk_band": item["risk_band"],
                    "propagation_risk": item["propagation_risk"],
                    "statement_count": item["statement_count"],
                    "cohort_resolution_state": resolution.get("resolution_state", ""),
                    "abstract_available": bool(span and span.get("abstract_available")),
                    "has_known_conflict": bool(item.get("known_conflicts")),
                    "estimated_effort": "alto" if item["statement_count"] > 3 else "medio",
                }
            )

        mapping.append(
            {
                "profile_unit_id": unit_id,
                "first_review_blind_id": first_id,
                "second_review_blind_id": second_id,
            }
        )

    write_csv(output / "first_review_queue.csv", first_rows, QUEUE_COLUMNS)
    write_csv(output / "second_review_queue.csv", second_rows, QUEUE_COLUMNS)
    write_json(
        output / "blind_id_mapping.json",
        {
            "created_at": created_at,
            "note": (
                "Mappa fra unita' e i due identificatori ciechi. Serve all'adjudication e "
                "NON va consegnata ai revisori: chi la possiede puo' allineare i due "
                "pacchetti e la seconda revisione smette di essere indipendente."
            ),
            "mapping": mapping,
        },
    )

    for name, rows, title in (
        ("FIRST_REVIEW_QUEUE.md", first_rows, "Coda di prima revisione"),
        ("SECOND_REVIEW_QUEUE.md", second_rows, "Coda di seconda revisione"),
    ):
        lines = [
            f"# {title}",
            "",
            f"{len(rows)} unita', ordinate per **rischio di propagazione errata**: quanto",
            "danno farebbe qui un qualificatore sbagliato. Il numero di proposizioni",
            "collegate e' il moltiplicatore del danno, quindi le fonti che ne sostengono",
            "molte vengono per prime.",
            "",
        ]
        if "SECOND" in name:
            lines += [
                "I pacchetti di questa coda **non** contengono la decisione del primo",
                "revisore. Mostrarla misurerebbe quanto il secondo annotatore concorda con",
                "il primo dopo averlo letto, che non e' un accordo fra revisioni",
                "indipendenti.",
                "",
            ]
        lines += [
            "| # | Pacchetto | Rischio | Statement | Coorte | Abstract | Conflitto |",
            "| ---: | --- | --- | ---: | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                f"| {row['queue_position']} | `{row['blind_annotation_id']}` | "
                f"{row['risk_band']} ({row['propagation_risk']}) | {row['statement_count']} | "
                f"`{row['cohort_resolution_state']}` | "
                f"{'sì' if row['abstract_available'] else 'no'} | "
                f"{'sì' if row['has_known_conflict'] else 'no'} |"
            )
        lines.append("")
        write_text(output / name, "\n".join(lines) + "\n")

    write_csv(
        output / "reviewer_assignment_template.csv",
        [
            {
                "blind_annotation_id": row["blind_annotation_id"],
                "review_round": "first_review",
                "assigned_reviewer_id": "",
                "assigned_at": "",
                "completed_at": "",
                "status": "unassigned",
            }
            for row in first_rows
        ]
        + [
            {
                "blind_annotation_id": row["blind_annotation_id"],
                "review_round": "second_review",
                "assigned_reviewer_id": "",
                "assigned_at": "",
                "completed_at": "",
                "status": "unassigned",
            }
            for row in second_rows
        ],
        (
            "blind_annotation_id",
            "review_round",
            "assigned_reviewer_id",
            "assigned_at",
            "completed_at",
            "status",
        ),
    )

    adjudication_rows = [
        {
            "profile_unit_id": item["profile_unit_id"],
            "first_review_blind_id": item["first_review_blind_id"],
            "second_review_blind_id": item["second_review_blind_id"],
            "first_annotator_id": "",
            "first_link_status": "",
            "second_annotator_id": "",
            "second_link_status": "",
            "agreement": None,
            "adjudicator_id": "",
            "adjudicated_link_status": "",
            "adjudication_rationale_codes": [],
            "adjudicated_at": "",
            "note": "template vuoto: nessuna revisione e' stata simulata",
        }
        for item in mapping
    ]
    write_jsonl(output / "adjudication_template.jsonl", adjudication_rows)
    write_csv(
        output / "adjudication_template.csv",
        adjudication_rows,
        (
            "profile_unit_id",
            "first_review_blind_id",
            "second_review_blind_id",
            "first_annotator_id",
            "first_link_status",
            "second_annotator_id",
            "second_link_status",
            "agreement",
            "adjudicator_id",
            "adjudicated_link_status",
            "adjudicated_at",
        ),
    )

    print(f"packet di prima revisione: {len(first_rows)}")
    print(f"packet di seconda revisione: {len(second_rows)}")
    print(f"mapping cieco: {len(mapping)} unita'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
