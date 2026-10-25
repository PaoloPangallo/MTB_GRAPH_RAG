"""Proiezione pertinente: selezione dei record canonici rilevanti per il caso.

Prima questa fase era soltanto dichiarata nella trace, senza alcun codice
corrispondente: il report candidato veniva reso direttamente dalla vista
canonica. Qui la proiezione esiste davvero, parte **esclusivamente** dalla
vista canonica (mai dallo stato in memoria) e registra criteri ed esito nel
ledger.

La proiezione non inventa dati: può soltanto ammettere o escludere record già
presenti nella vista, motivando ogni esclusione.
"""

from __future__ import annotations

from typing import Sequence

from backend.pipeline.control.claim_grammar import entities_for, lexicon_for
from backend.pipeline.control.contracts import (
    CanonicalRecord,
    CanonicalView,
    CaseContext,
    Projection,
    ProjectedRecord,
)

#: Tipi di record che entrano nel report come claim. ``drug`` e ``oncokb``
#: sono materiale di supporto: informano il dossier ma non generano claim
#: citabili, perché non portano una fonte propria.
CLAIM_KINDS = frozenset({"evidence", "resistance", "trial"})

#: Livelli di evidenza ammessi, coerenti con le query Cypher del retrieval.
ACCEPTED_EVIDENCE_LEVELS = frozenset({"A", "B", "LEVEL_1", "LEVEL_2", "1", "2"})

#: Strumenti obbligatori per obiettivo, e quindi tipi di record attesi. Serve
#: a distinguere "non pertinente" da "non raccolto".
GOAL_RECORD_KINDS: dict[str, frozenset[str]] = {
    "general-review": frozenset({"evidence", "resistance", "trial"}),
    "treatment-evidence": frozenset({"evidence"}),
    "resistance": frozenset({"evidence", "resistance"}),
    "clinical-trials": frozenset({"evidence", "trial"}),
}


def _goal_kinds(mtb_goal: str | None) -> frozenset[str]:
    return GOAL_RECORD_KINDS.get(mtb_goal or "", GOAL_RECORD_KINDS["general-review"])


def _required_citation(record: CanonicalRecord) -> str | None:
    source = record.original_claim.source_id
    if not source:
        return None
    if record.record_kind == "trial" and not source.startswith("NCT"):
        return None
    return source


def _evaluate(record: CanonicalRecord, case: CaseContext, goal_kinds: frozenset[str]) -> tuple[bool, str | None]:
    """Decide se un record entra nel report candidato, e perché no in caso contrario."""
    if record.record_kind not in CLAIM_KINDS:
        return False, f"Record di tipo '{record.record_kind}': materiale di supporto, non genera claim citabili."

    if record.record_kind not in goal_kinds:
        return False, (
            f"Tipo '{record.record_kind}' non pertinente all'obiettivo MTB "
            f"'{case.mtb_goal or 'general-review'}'."
        )

    if _required_citation(record) is None:
        return False, "Record privo di una fonte citabile: non verificabile documentalmente."

    if record.record_kind == "evidence":
        level = (record.original_claim.evidence_level or "").strip().upper()
        if level and level not in ACCEPTED_EVIDENCE_LEVELS:
            return False, f"Livello di evidenza '{level}' fuori dall'insieme ammesso."

    return True, None


def project_for_case(view: CanonicalView, case: CaseContext) -> Projection:
    """Seleziona dalla vista canonica i record pertinenti al caso e all'obiettivo."""
    goal_kinds = _goal_kinds(case.mtb_goal)

    records: list[ProjectedRecord] = []
    for record in view.records:
        admitted, reason = _evaluate(record, case, goal_kinds)
        records.append(
            ProjectedRecord(
                canonical_record_id=record.canonical_record_id,
                record_kind=record.record_kind,
                claim=record.original_claim,
                admitted=admitted,
                exclusion_reason=reason,
                required_citation=_required_citation(record),
                lexicon=lexicon_for(record.original_claim),
                entities=entities_for(record.original_claim),
                conflict_annotations=record.conflict_annotations,
                provenance=record.provenance,
            )
        )

    return Projection(
        run_id=view.run_id,
        case_label=case.label(),
        records=tuple(records),
        criteria=_criteria(case, goal_kinds),
        completeness_status=view.completeness_status,
    )


def _criteria(case: CaseContext, goal_kinds: frozenset[str]) -> tuple[str, ...]:
    return (
        f"Obiettivo MTB: {case.mtb_goal or 'general-review'}.",
        f"Tipi di record pertinenti: {', '.join(sorted(goal_kinds))}.",
        f"Livelli di evidenza ammessi: {', '.join(sorted(ACCEPTED_EVIDENCE_LEVELS))}.",
        "Ogni record ammesso deve portare una fonte citabile (PMID o NCT).",
    )


def projection_payload(projection: Projection) -> dict:
    """Payload per il ledger: criteri applicati ed esito record per record."""
    return {
        "criteria": list(projection.criteria),
        "records_in": len(projection.records),
        "admitted": len(projection.admitted),
        "excluded": len(projection.excluded),
        "completeness_status": projection.completeness_status,
        "admitted_ids": sorted(projection.admitted_ids),
        "exclusions": [
            {
                "canonical_record_id": record.canonical_record_id,
                "record_kind": record.record_kind,
                "reason": record.exclusion_reason,
            }
            for record in projection.excluded
        ],
    }


def evidence_items_from(projection: Projection) -> list:
    """Adatta i record ammessi al modello ``EvidenceItem`` dell'API.

    Il source verifier lavora ancora su ``EvidenceItem``; l'adattamento resta
    confinato qui invece di far conoscere il modello dell'API a tutto lo strato
    di controllo.
    """
    from backend.api.schemas import EvidenceItem

    items = []
    for record in projection.admitted:
        claim = record.claim
        items.append(
            EvidenceItem(
                subject=claim.subject,
                relation=claim.relation,
                object=claim.object,
                context=claim.context,
                source_id=claim.source_id,
                provenance=_provenance_text(record.provenance),
                evidence_statement=claim.evidence_statement,
                citation_text=claim.citation_text,
                evidence_level=claim.evidence_level,
            )
        )
    return items


def _provenance_text(refs: Sequence) -> str:
    if not refs:
        return "Provenienza non registrata."
    tools = sorted({ref.tool_name for ref in refs if ref.tool_name})
    origin = ", ".join(tools) if tools else "strumento non dichiarato"
    return f"Osservato da {origin} in {len(refs)} azione/i registrate nel ledger."
