"""Identità, fusione e annotazione dei conflitti fra record canonici.

La deduplicazione precedente teneva il primo record e scartava gli altri,
perdendo la genealogia: dopo il merge non era più possibile sapere quali
azioni avessero osservato lo stesso fatto, né se fossero in disaccordo.

Qui la deduplicazione **fonde** le osservazioni: ogni occorrenza resta
registrata con la propria provenienza, la claim originale è fissata alla prima
osservazione e non viene mai riscritta, e i disaccordi sui campi non identitari
diventano annotazioni esplicite invece di sparire.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.control.contracts import (
    CanonicalRecord,
    CompletenessStatus,
    ConflictAnnotation,
    OriginalClaim,
    ProvenanceRef,
    RecordObservation,
)

_WHITESPACE = re.compile(r"\s+")

#: Ordine di severità: la completezza si propaga in modo pessimistico, perché
#: una vista costruita anche su una sola azione troncata è essa stessa
#: incompleta e non deve presentarsi come completa.
_COMPLETENESS_RANK: dict[str, int] = {
    "truncated": 0,
    "partial": 1,
    "unknown": 2,
    "complete": 3,
}

#: Campi confrontati per rilevare disaccordi fra osservazioni dello stesso
#: record. Solo campi **strutturati**: una divergenza qui è informazione
#: clinica.
#:
#: I campi in prosa (``evidence_statement``, ``citation_text``, ``title``) sono
#: deliberatamente esclusi. Due curazioni CIViC dello stesso studio lo
#: descrivono spesso con parole diverse: segnalarlo come conflitto manderebbe
#: al MTB rumore invece di un disaccordo reale, e finirebbe per abituarlo a
#: ignorare le annotazioni di conflitto.
_CONFLICT_FIELDS: Mapping[str, tuple[str, ...]] = {
    "evidence": ("evidence_level", "significance"),
    "trial": ("phase", "status", "drug_tested"),
    "resistance": ("evidence_level", "significance", "drug_name"),
    "drug": ("evidence_level", "approved"),
    "oncokb": ("oncogenic", "level"),
}


def normalize(value: Any) -> str:
    """Casefold + collasso degli spazi.

    Il confronto precedente era case-sensitive, quindi ``OSIMERTINIB`` e
    ``osimertinib`` sopravvivevano come due record distinti dello stesso fatto.
    """
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value).strip()).casefold()


def _source_id(record: Mapping[str, Any]) -> str | None:
    pmid = record.get("pmid")
    if pmid:
        return f"PMID:{pmid}"
    source = record.get("source_id")
    return str(source) if source else None


def _therapies_text(record: Mapping[str, Any]) -> str:
    """Terapie del record di evidenza, nella forma resa nel report.

    Neo4j restituisce ``therapies`` come lista; quando è assente si ricade sul
    profilo molecolare, come faceva la costruzione originale delle evidenze.
    """
    therapies = record.get("therapies")
    if isinstance(therapies, str):
        therapies = [therapies]
    values = sorted(str(item) for item in (therapies or []) if item)
    if values:
        return ", ".join(values)
    return str(record.get("molecular_profile") or "clinical evidence")


def evidence_subject(record: Mapping[str, Any]) -> str:
    return str(record.get("subject") or record.get("molecular_profile") or "")


def evidence_object(record: Mapping[str, Any]) -> str:
    return str(record.get("object") or _therapies_text(record))


def evidence_relation(record: Mapping[str, Any]) -> str:
    return str(record.get("relation") or record.get("significance") or "evidence")


def evidence_context(record: Mapping[str, Any]) -> str:
    return str(record.get("context") or record.get("disease") or record.get("tumor_type") or "")


def identity_key(record_kind: str, record: Mapping[str, Any]) -> tuple[str, ...]:
    """Chiave d'identità normalizzata, specifica per tipo di record.

    I trial si identificano dal solo NCT ID: lo stesso studio recuperato con
    query diverse è lo stesso studio. Le resistenze dalla coppia
    ``(variante, fonte)``. Le evidenze dalla tripla semantica più la fonte.
    """
    if record_kind == "trial":
        return ("trial", normalize(record.get("nct_id")))
    if record_kind == "resistance":
        return ("resistance", normalize(record.get("variant")), normalize(_source_id(record)))
    if record_kind == "drug":
        return ("drug", normalize(record.get("drug_name")))
    if record_kind == "oncokb":
        return ("oncokb", normalize(record.get("gene")), normalize(record.get("variant")))
    return (
        "evidence",
        normalize(evidence_subject(record)),
        normalize(evidence_relation(record)),
        normalize(evidence_object(record)),
        normalize(evidence_context(record)),
        normalize(_source_id(record)),
    )


def canonical_record_id(key: Sequence[str]) -> str:
    """Identificatore stabile fra run, derivato dalla sola identità.

    Gli id precedenti erano posizionali (``PMID:x-3``), quindi due run non
    erano confrontabili: bastava un record in più a monte per rinominarli
    tutti. Un hash dell'identità rende il confronto fra architetture possibile.
    """
    digest = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()
    return digest[:16]


def original_claim(record_kind: str, record: Mapping[str, Any]) -> OriginalClaim:
    if record_kind == "trial":
        return OriginalClaim(
            subject=str(record.get("nct_id") or ""),
            relation="CLINICAL_TRIAL",
            object=str(record.get("drug_tested") or ""),
            context=str(record.get("title") or ""),
            source_id=str(record.get("nct_id")) if record.get("nct_id") else None,
        )
    if record_kind == "resistance":
        return OriginalClaim(
            subject=str(record.get("variant") or ""),
            relation="RESISTANCE",
            object=str(record.get("drug_name") or ""),
            context=str(record.get("significance") or ""),
            source_id=_source_id(record),
            evidence_level=record.get("evidence_level"),
        )
    return OriginalClaim(
        subject=evidence_subject(record),
        relation=evidence_relation(record),
        object=evidence_object(record),
        context=evidence_context(record),
        source_id=_source_id(record),
        evidence_statement=record.get("evidence_statement"),
        citation_text=record.get("citation_text"),
        evidence_level=record.get("evidence_level"),
    )


def weakest_completeness(statuses: Iterable[str]) -> CompletenessStatus:
    values = [s for s in statuses if s]
    if not values:
        return "unknown"
    return min(values, key=lambda s: _COMPLETENESS_RANK.get(s, 2))  # type: ignore[return-value]


def detect_conflicts(
    record_kind: str,
    observations: Sequence[RecordObservation],
) -> tuple[ConflictAnnotation, ...]:
    """Annota i campi su cui le osservazioni non concordano.

    Non risolve il conflitto: scegliere silenziosamente un valore nasconderebbe
    al MTB un disaccordo fra fonti, che è esattamente ciò che deve vedere.
    """
    if len(observations) < 2:
        return ()

    conflicts: list[ConflictAnnotation] = []
    for field_name in _CONFLICT_FIELDS.get(record_kind, ()):
        by_value: dict[str, list[ProvenanceRef]] = {}
        for observation in observations:
            raw = observation.payload.get(field_name)
            if raw in (None, ""):
                continue
            by_value.setdefault(str(raw), []).append(observation.provenance)
        if len(by_value) > 1:
            conflicts.append(
                ConflictAnnotation(
                    field_name=field_name,
                    values=tuple(sorted(by_value)),
                    provenance=tuple(ref for refs in by_value.values() for ref in refs),
                )
            )
    return tuple(conflicts)


def merge_observations(
    record_kind: str,
    key: Sequence[str],
    observations: Sequence[RecordObservation],
    completeness: Sequence[str],
) -> CanonicalRecord:
    """Fonde le osservazioni di uno stesso fatto conservandone la genealogia."""
    first = observations[0]
    return CanonicalRecord(
        canonical_record_id=canonical_record_id(key),
        record_kind=record_kind,  # type: ignore[arg-type]
        identity_key=tuple(key),
        original_claim=original_claim(record_kind, first.payload),
        observations=tuple(observations),
        source_event_ids=tuple(o.provenance.event_id for o in observations),
        source_action_ids=tuple(
            o.provenance.action_id for o in observations if o.provenance.action_id
        ),
        provenance=tuple(o.provenance for o in observations),
        conflict_annotations=detect_conflicts(record_kind, observations),
        completeness_status=weakest_completeness(completeness),
    )
