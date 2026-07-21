"""Costruzione dello snapshot gold a partire dal clinical gold e dall'audit.

Lo snapshot gold risponde a una domanda diversa dal clinical gold: non "che cosa e'
vero secondo la letteratura" ma "che cosa e' presente e raggiungibile in *questo*
grafo". La distinzione e' il perno dell'intera valutazione.

Un elemento clinico puo' trovarsi in quattro stati:

- `present` — c'e', ed e' raggiungibile dal traversal;
- `partially_present` — c'e' ma incompleto: tipicamente un PMID che esiste solo come
  `Evidence.citation_id` senza nodo `Publication`, oppure un farmaco che esiste come
  nodo ma non e' raggiungibile dal profilo del caso;
- `absent` — non c'e';
- `ambiguous` — c'e' qualcosa di correlato ma con un conflitto che ne impedisce
  l'equiparazione, per esempio un sottotipo di malattia diverso.

Solo `present` e `partially_present`, e solo se raggiungibili, possono essere
pretesi dal retriever. Il resto abbassa la copertura del grafo, non il recall.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..pilot.audit_lib.normalize import norm_drug, norm_nct_set, norm_pmid_set, norm_text
from .contracts import (
    ABSENT,
    AMBIGUOUS,
    PARTIALLY_PRESENT,
    PRESENT,
    ClinicalGoldCase,
    SnapshotGoldCase,
    SnapshotGoldClaim,
)

KIND_THERAPY = "therapy"
KIND_PMID = "pmid"
KIND_NCT = "nct_id"
KIND_CLAIM = "claim"
KIND_ENTITY = "entity"
KIND_QUALIFIER = "qualifier"


class SnapshotGoldError(RuntimeError):
    """Gli artefatti di audit richiesti non sono disponibili o non sono coerenti."""


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise SnapshotGoldError(f"artefatto di audit mancante: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class AuditArtifacts:
    """Accesso agli artefatti prodotti dall'audit del grafo."""

    def __init__(self, audit_dir: Path) -> None:
        self.audit_dir = Path(audit_dir)
        self.manifest = _read_json(self.audit_dir / "graph_snapshot_manifest.json")

    @property
    def fingerprint(self) -> str:
        return str(self.manifest.get("snapshot_fingerprint", {}).get("value", ""))

    def comparison(self, case_id: str) -> dict[str, Any]:
        return _read_json(self.audit_dir / case_id / "comparison_with_gold.json")

    def normalized_records(self, case_id: str) -> list[dict[str, Any]]:
        return _read_jsonl(self.audit_dir / case_id / "normalized_records.jsonl")

    def entities(self, case_id: str) -> dict[str, Any]:
        path = self.audit_dir / case_id / "graph_entities.json"
        return _read_json(path) if path.is_file() else {}

    def negative_proof(self, case_id: str) -> dict[str, Any] | None:
        path = self.audit_dir / case_id / "negative_path_proof.json"
        return _read_json(path) if path.is_file() else None


def _therapy_items(
    case: ClinicalGoldCase,
    comparison: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    alias_table: Mapping[str, str],
    entities: Mapping[str, Any],
) -> list[SnapshotGoldClaim]:
    """Stato di ogni terapia attesa: presente, raggiungibile, o solo esistente.

    La distinzione fra "il nodo Drug esiste" e "il traversal lo raggiunge" e' quella
    che il caso K1 rende necessaria: futibatinib esiste come farmaco nello snapshot
    ma nessun percorso del caso vi arriva. Sono due gradi di copertura diversi.
    """
    found = {norm_text(item) for item in comparison.get("found_therapies", [])}
    missing = {norm_text(item) for item in comparison.get("missing_therapies", [])}
    drug_nodes = {
        norm_drug(entry.get("drug_name"), dict(alias_table))
        for entry in ((entities.get("entities") or {}).get("expected_drugs_found") or [])
    }

    items: list[SnapshotGoldClaim] = []
    for therapy in case.expected_therapies:
        name = norm_drug(therapy, dict(alias_table))
        record_ids = tuple(
            str(record.get("record_id", ""))
            for record in records
            if norm_text(record.get("drug")) == name
        )
        if name in found and record_ids:
            status, reachable, notes = PRESENT, True, ()
        elif name in found:
            status, reachable, notes = (
                PARTIALLY_PRESENT,
                True,
                ("terapia riportata dall'audit ma senza record normalizzati associati",),
            )
        elif name in drug_nodes:
            status, reachable, notes = (
                PARTIALLY_PRESENT,
                False,
                (
                    "il nodo Drug esiste nel grafo ma non e' raggiungibile dal profilo "
                    "del caso: il traversal non lo tocca",
                ),
            )
        else:
            status, reachable, notes = (
                ABSENT,
                False,
                ("terapia non presente nello snapshot",),
            )
        items.append(
            SnapshotGoldClaim(
                clinical_item_id=f"{case.case_id}::therapy::{name}",
                case_id=case.case_id,
                item_kind=KIND_THERAPY,
                presence_status=status,
                graph_record_ids=record_ids,
                reachable_by_fixed_plan=reachable,
                reachable_by_agentic_tools=reachable,
                missing_fields=() if status == PRESENT else ("graph_path",),
                coverage_notes=notes,
            )
        )
    return items


def _pmid_items(
    case: ClinicalGoldCase,
    comparison: Mapping[str, Any],
    entities: Mapping[str, Any],
) -> list[SnapshotGoldClaim]:
    """Stato di ogni PMID atteso, distinguendo nodo Publication da sola citazione.

    E' la distinzione che l'audit ha reso necessaria: per il caso A2 tutti i PMID
    attesi esistono soltanto dentro `Evidence.citation_id`. Sono recuperabili, ma non
    come nodo bibliografico, e chiamarli semplicemente "presenti" nasconderebbe un
    limite reale del grafo.
    """
    discovery = (entities.get("entities") or {}).get("pmid_discovery") or {}
    as_node = set(discovery.get("as_publication_node") or [])
    as_citation = set(discovery.get("as_evidence_citation") or [])
    missing = set(comparison.get("missing_pmids") or [])

    items: list[SnapshotGoldClaim] = []
    for pmid in norm_pmid_set(case.expected_pmids):
        if pmid in as_node:
            status, notes = PRESENT, ("presente come nodo Publication",)
            missing_fields: tuple[str, ...] = ()
        elif pmid in as_citation:
            status = PARTIALLY_PRESENT
            notes = (
                "presente solo dentro Evidence.citation_id: recuperabile come "
                "citazione, ma senza nodo Publication",
            )
            missing_fields = ("publication_node",)
        elif pmid in missing:
            status, notes, missing_fields = (
                ABSENT,
                ("assente dallo snapshot in qualunque forma",),
                ("publication_node", "citation"),
            )
        else:
            status, notes, missing_fields = (
                AMBIGUOUS,
                ("non classificabile dagli artefatti di audit disponibili",),
                (),
            )
        reachable = status in {PRESENT, PARTIALLY_PRESENT}
        items.append(
            SnapshotGoldClaim(
                clinical_item_id=f"{case.case_id}::pmid::{pmid}",
                case_id=case.case_id,
                item_kind=KIND_PMID,
                presence_status=status,
                graph_source_ids=(f"PMID:{pmid}",) if reachable else (),
                reachable_by_fixed_plan=reachable,
                reachable_by_agentic_tools=reachable,
                missing_fields=missing_fields,
                coverage_notes=notes,
            )
        )
    return items


def _nct_items(case: ClinicalGoldCase, comparison: Mapping[str, Any]) -> list[SnapshotGoldClaim]:
    found = set(comparison.get("found_nct_ids") or [])
    missing = set(comparison.get("missing_nct_ids") or [])
    items: list[SnapshotGoldClaim] = []
    for nct in norm_nct_set(case.expected_nct_ids):
        if nct in found:
            status, notes = PRESENT, ("nodo ClinicalTrial presente",)
        elif nct in missing:
            status, notes = ABSENT, ("nessun nodo ClinicalTrial con questo nct_id",)
        else:
            status, notes = AMBIGUOUS, ("non classificabile dagli artefatti disponibili",)
        reachable = status == PRESENT
        items.append(
            SnapshotGoldClaim(
                clinical_item_id=f"{case.case_id}::nct::{nct}",
                case_id=case.case_id,
                item_kind=KIND_NCT,
                presence_status=status,
                graph_source_ids=(nct,) if reachable else (),
                reachable_by_fixed_plan=reachable,
                reachable_by_agentic_tools=reachable,
                missing_fields=() if reachable else ("clinical_trial_node",),
                coverage_notes=notes,
            )
        )
    return items


def _claim_items(
    case: ClinicalGoldCase, comparison: Mapping[str, Any]
) -> list[SnapshotGoldClaim]:
    """Stato di ogni claim clinica secondo il confronto dell'audit."""
    by_level: dict[str, str] = {}
    conflicts_by_claim: dict[str, list[str]] = {}
    records_by_claim: dict[str, list[str]] = {}

    for level, key in (
        (PRESENT, "structurally_matching_claims"),
        (PARTIALLY_PRESENT, "partially_matching_claims"),
        (ABSENT, "unmatched_claims"),
    ):
        for match in comparison.get(key) or []:
            claim_id = str(match.get("claim_id"))
            by_level[claim_id] = level
            records_by_claim[claim_id] = [
                str(item) for item in match.get("matched_record_ids") or []
            ]
            conflicts_by_claim[claim_id] = [
                str(item) for item in match.get("conflicting_dimensions") or []
            ]

    items: list[SnapshotGoldClaim] = []
    for claim in case.expected_claims:
        level = by_level.get(claim.claim_id, AMBIGUOUS)
        conflicts = tuple(conflicts_by_claim.get(claim.claim_id, ()))
        # Una claim con conflitti di qualificatore non e' semplicemente parziale:
        # il grafo dice qualcosa di diverso, e va marcata come ambigua.
        if conflicts and level == PARTIALLY_PRESENT:
            level = AMBIGUOUS
        reachable = level in {PRESENT, PARTIALLY_PRESENT}
        items.append(
            SnapshotGoldClaim(
                clinical_item_id=claim.claim_id,
                case_id=case.case_id,
                item_kind=KIND_CLAIM,
                presence_status=level,
                graph_record_ids=tuple(records_by_claim.get(claim.claim_id, ())),
                reachable_by_fixed_plan=reachable,
                reachable_by_agentic_tools=reachable,
                conflicting_fields=conflicts,
                coverage_notes=(
                    f"livello di corrispondenza dell'audit: {level}",
                ) + (
                    (f"conflitti: {list(conflicts)}",) if conflicts else ()
                ),
            )
        )
    return items


def _qualifier_items(
    case: ClinicalGoldCase, comparison: Mapping[str, Any]
) -> list[SnapshotGoldClaim]:
    """Qualificatori: distingue cio' che lo schema non modella da cio' che manca.

    Sono due limiti diversi. `not_modelled_by_schema` non e' recuperabile da nessuna
    architettura, e pretenderlo dal retriever misurerebbe l'infrastruttura invece del
    sistema.
    """
    not_modelled = set(comparison.get("not_modelled_by_schema") or [])
    missing_entries = comparison.get("qualifiers_missing") or []
    absent_dimensions = {
        str(entry.get("dimension"))
        for entry in missing_entries
        if entry.get("status") == "absent_in_record"
    }

    items: list[SnapshotGoldClaim] = []
    for dimension in sorted(not_modelled | absent_dimensions):
        modelled = dimension not in not_modelled
        items.append(
            SnapshotGoldClaim(
                clinical_item_id=f"{case.case_id}::qualifier::{dimension}",
                case_id=case.case_id,
                item_kind=KIND_QUALIFIER,
                presence_status=ABSENT,
                reachable_by_fixed_plan=False,
                reachable_by_agentic_tools=False,
                missing_fields=(dimension,),
                coverage_notes=(
                    "assente dal record ma rappresentabile dallo schema"
                    if modelled
                    else "non modellato dallo schema: nessuna architettura puo' recuperarlo",
                ),
            )
        )
    return items


def build_snapshot_gold(
    case: ClinicalGoldCase,
    artifacts: AuditArtifacts,
    *,
    alias_table: Mapping[str, str] | None = None,
) -> SnapshotGoldCase:
    """Costruisce lo snapshot gold di un caso dagli artefatti dell'audit."""
    comparison = artifacts.comparison(case.case_id)
    records = artifacts.normalized_records(case.case_id)
    entities = artifacts.entities(case.case_id)
    aliases = dict(alias_table or {})

    items: list[SnapshotGoldClaim] = []
    items.extend(_therapy_items(case, comparison, records, aliases, entities))
    items.extend(_pmid_items(case, comparison, entities))
    items.extend(_nct_items(case, comparison))
    items.extend(_claim_items(case, comparison))
    items.extend(_qualifier_items(case, comparison))

    notes: list[str] = []
    proof = artifacts.negative_proof(case.case_id)
    if proof is not None:
        notes.append(
            f"prova negativa archiviata: percorsi terapeutici = "
            f"{proof.get('therapeutic_path_count')}, valida = {proof.get('is_valid_negative')}"
        )
    for warning in comparison.get("audit_warnings") or []:
        notes.append(str(warning))

    retrievable = [item for item in items if item.is_retrievable]
    return SnapshotGoldCase(
        case_id=case.case_id,
        snapshot_fingerprint=artifacts.fingerprint,
        items=tuple(items),
        retrievable_therapies=tuple(
            sorted(
                item.clinical_item_id.rsplit("::", 1)[-1]
                for item in retrievable
                if item.item_kind == KIND_THERAPY
            )
        ),
        retrievable_pmids=tuple(
            sorted(
                item.clinical_item_id.rsplit("::", 1)[-1]
                for item in retrievable
                if item.item_kind == KIND_PMID
            )
        ),
        retrievable_nct_ids=tuple(
            sorted(
                item.clinical_item_id.rsplit("::", 1)[-1]
                for item in retrievable
                if item.item_kind == KIND_NCT
            )
        ),
        expected_abstention=case.expected_abstention,
        notes=tuple(notes),
    )


def mapping_rows(
    clinical: Sequence[ClinicalGoldCase], snapshot: Sequence[SnapshotGoldCase]
) -> list[dict[str, Any]]:
    """Righe del mapping clinico -> snapshot, una per elemento clinico."""
    by_case = {case.case_id: case for case in snapshot}
    rows: list[dict[str, Any]] = []
    for case in clinical:
        snap = by_case.get(case.case_id)
        if snap is None:
            continue
        for item in snap.items:
            rows.append(
                {
                    "case_id": case.case_id,
                    "clinical_item_id": item.clinical_item_id,
                    "item_kind": item.item_kind,
                    "presence_status": item.presence_status,
                    "is_retrievable": item.is_retrievable,
                    "reachable_by_fixed_plan": item.reachable_by_fixed_plan,
                    "reachable_by_agentic_tools": item.reachable_by_agentic_tools,
                    "graph_record_ids": list(item.graph_record_ids),
                    "graph_source_ids": list(item.graph_source_ids),
                    "missing_fields": list(item.missing_fields),
                    "conflicting_fields": list(item.conflicting_fields),
                    "coverage_notes": list(item.coverage_notes),
                    "snapshot_fingerprint": snap.snapshot_fingerprint,
                }
            )
    return rows


def presence_summary(cases: Iterable[SnapshotGoldCase]) -> dict[str, dict[str, int]]:
    """Conteggio degli stati di presenza per tipo di elemento."""
    summary: dict[str, dict[str, int]] = {}
    for case in cases:
        for item in case.items:
            bucket = summary.setdefault(item.item_kind, {})
            bucket[item.presence_status] = bucket.get(item.presence_status, 0) + 1
    return {kind: dict(sorted(states.items())) for kind, states in sorted(summary.items())}
