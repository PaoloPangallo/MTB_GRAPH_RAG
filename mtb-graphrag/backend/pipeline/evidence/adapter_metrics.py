"""Misure di fedelta' dell'adapter V2 → EvidenceStatement.

Il criterio non e' «il 95% dei qualificatori e' presente»: molti qualificatori non
esistono affatto nei record V2, ed e' proprio il punto di partenza che la V3 vuole
cambiare. Il criterio e':

> almeno il 95% dei record V2 **compatibili** deve poter essere trasformato in un
> EvidenceStatement valido, senza perdere i campi effettivamente disponibili nel
> record originale.

Quattro misure, che rispondono a quattro domande diverse.

| Misura | Domanda |
| --- | --- |
| `conversion_success_rate` | quanti record compatibili diventano statement validi? |
| `source_field_preservation` | dei campi presenti nel record, quanti sopravvivono? |
| `provenance_preservation` | ogni statement resta riconducibile al record originale? |
| `unknown_field_honesty` | un dato assente e' rimasto assente, o e' stato dedotto? |

L'ultima e' la piu' importante e la meno ovvia. Un adapter che riempisse i vuoti con
valori plausibili otterrebbe punteggi migliori su tutte le altre tre, e falsificherebbe
la baseline: la V3 sembrerebbe partire da un grafo piu' ricco di quello reale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .v2_adapter import AdaptationResult, is_evidence_record, merge_duplicate_records

# Campi del record V2 che, se presenti, devono comparire nello statement. Sono i campi
# che il grafo effettivamente porta: chiedere di piu' misurerebbe il grafo, non
# l'adapter.
SOURCE_FIELDS_TO_PRESERVE = (
    ("molecular_profile", "biomarker.label"),
    ("disease", "disease.label"),
    ("drug", "intervention.label"),
    ("significance", "direction"),
    ("evidence_direction", "assertion_polarity"),
    ("evidence_type", "evidence_scope"),
    ("evidence_level", "evidence_level"),
    ("citation_id", "source_references"),
)

# Campi dello statement che non devono mai essere valorizzati partendo da un record
# che non li contiene. Sono il cuore di `unknown_field_honesty`.
FIELDS_THAT_MUST_STAY_UNKNOWN = (
    "clinical_context.disease_setting",
    "clinical_context.stage",
    "clinical_context.therapy_line",
    "clinical_context.resection_status",
    "clinical_context.population",
    "evidence_type",
)


@dataclass(frozen=True)
class Measure:
    name: str
    numerator: float
    denominator: float
    detail: tuple[str, ...] = ()
    note: str = ""

    @property
    def value(self) -> float | None:
        return self.numerator / self.denominator if self.denominator else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "detail": list(self.detail[:20]),
            "note": self.note,
        }


def compatible_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """I record che possono in linea di principio diventare uno statement.

    Sono quelli di evidenza con almeno una citazione. Un record di trial descrive uno
    studio, non una proposizione clinica, e diventera' un `trial_reference` di altri
    statement: contarlo fra i fallimenti di conversione misurerebbe la cosa sbagliata.
    """
    return [
        record
        for record in records
        if is_evidence_record(record) and (record.get("citation_id") or record.get("pmids"))
    ]


def conversion_success_rate(results: Sequence[AdaptationResult]) -> Measure:
    converted = [r for r in results if r.converted]
    failed = [r for r in results if not r.converted]
    return Measure(
        name="conversion_success_rate",
        numerator=len(converted),
        denominator=len(results),
        detail=tuple(f"{r.record_id}: {r.reason}" for r in failed),
        note="denominatore: record compatibili, non tutti i record del grafo",
    )


def source_field_preservation(
    results: Sequence[AdaptationResult], records: Sequence[Mapping[str, Any]]
) -> Measure:
    """Dei campi presenti nel record originale, quanti sopravvivono nello statement."""
    by_id = _index(records)
    preserved = expected = 0
    lost: list[str] = []

    for result in results:
        if not result.converted or result.statement is None:
            continue
        record = by_id.get(result.record_id, {})
        preserved_names = set(result.preserved_fields)
        for source_field, target_field in SOURCE_FIELDS_TO_PRESERVE:
            if not record.get(source_field):
                continue  # assente all'origine: non e' una perdita
            expected += 1
            if target_field in preserved_names:
                preserved += 1
            else:
                lost.append(f"{result.record_id}: {source_field} -> {target_field}")

    return Measure(
        name="source_field_preservation",
        numerator=preserved,
        denominator=expected,
        detail=tuple(lost),
        note="denominatore: solo i campi effettivamente presenti nel record originale",
    )


def provenance_preservation(results: Sequence[AdaptationResult]) -> Measure:
    """Ogni statement resta riconducibile al record da cui viene."""
    converted = [r for r in results if r.converted and r.statement is not None]
    traceable: list[str] = []
    broken: list[str] = []
    for result in converted:
        provenance = result.statement.get("provenance") or {}
        record_ids = provenance.get("graph_record_ids") or []
        has_origin = provenance.get("origin") == "frozen_kg"
        has_extraction = bool(provenance.get("extraction_action_id"))
        if record_ids and result.record_id in record_ids and has_origin and has_extraction:
            traceable.append(result.record_id)
        else:
            broken.append(result.record_id)
    return Measure(
        name="provenance_preservation",
        numerator=len(traceable),
        denominator=len(converted),
        detail=tuple(broken),
        note="richiede graph_record_ids, origin e extraction_action_id",
    )


def unknown_field_honesty(
    results: Sequence[AdaptationResult], records: Sequence[Mapping[str, Any]]
) -> Measure:
    """Un campo assente nel record e' rimasto assente nello statement?

    Controlla le due direzioni della disonestita':

    1. **invenzione** — un campo che il grafo non modella affatto compare valorizzato;
    2. **deduzione** — un campo assente in *quel* record compare valorizzato perche'
       dedotto da un altro campo.

    Il caso piu' insidioso e' `evidence_type`: il grafo non porta il disegno dello
    studio, e sarebbe facile inferirlo dal livello di evidenza. Un livello alto non
    implica uno studio randomizzato, e quella inferenza produrrebbe un dato che nessuna
    fonte sostiene.
    """
    by_id = _index(records)
    honest = checked = 0
    violations: list[str] = []

    for result in results:
        if not result.converted or result.statement is None:
            continue
        statement = result.statement
        record = by_id.get(result.record_id, {})

        # 1. Campi che devono restare non valorizzati.
        for path in FIELDS_THAT_MUST_STAY_UNKNOWN:
            checked += 1
            value = _resolve(statement, path)
            if value in (None, "", "unknown", {}, []):
                honest += 1
            else:
                violations.append(f"{result.record_id}: {path} = {value!r} ma non e' nel record")

        # 2. evidence_level assente all'origine non deve comparire.
        checked += 1
        if not record.get("evidence_level") and statement.get("evidence_level") is not None:
            violations.append(f"{result.record_id}: evidence_level dedotto")
        else:
            honest += 1

        # 3. Il livello presente deve conservare il valore originale, non normalizzarlo.
        if record.get("evidence_level"):
            checked += 1
            level = statement.get("evidence_level") or {}
            if str(level.get("original_value")) == str(record["evidence_level"]):
                honest += 1
            else:
                violations.append(f"{result.record_id}: evidence_level alterato")

    return Measure(
        name="unknown_field_honesty",
        numerator=honest,
        denominator=checked,
        detail=tuple(violations),
        note="verifica che l'assenza non sia stata riempita ne' dedotta",
    )


def _index(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Indicizza i record **dopo** la fusione dei duplicati.

    Le misure devono confrontare gli statement con esattamente gli stessi record che
    l'adapter ha convertito. Indicizzare i record grezzi farebbe vincere l'ultima
    occorrenza, mentre l'adapter ne usa la fusione, e le due letture divergerebbero:
    un campo presente nella fusione ma assente nell'ultima occorrenza verrebbe
    segnalato come dedotto pur essendo autentico.
    """
    return {
        str(record.get("record_id") or f"evidence:{record.get('evidence_id')}"): record
        for record in merge_duplicate_records(records)
    }


def _resolve(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def source_presence_breakdown(results: Sequence[AdaptationResult]) -> dict[str, int]:
    """Conteggio dei tre stati di presenza delle fonti nello snapshot.

    E' la distinzione emersa dall'audit: un PMID puo' essere un nodo Publication,
    comparire solo dentro Evidence.citation_id, o essere assente. Sono tre gradi di
    copertura diversi e appiattirli nasconderebbe la differenza.
    """
    counts: dict[str, int] = {}
    for result in results:
        if not result.converted or result.statement is None:
            continue
        for reference in result.statement.get("source_references", []):
            state = reference.get("presence_in_snapshot", "unknown")
            counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def evaluate(
    results: Sequence[AdaptationResult], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Le quattro misure piu' la ripartizione della presenza delle fonti."""
    measures = [
        conversion_success_rate(results),
        source_field_preservation(results, records),
        provenance_preservation(results),
        unknown_field_honesty(results, records),
    ]
    return {
        "measures": {measure.name: measure.as_dict() for measure in measures},
        "source_presence_breakdown": source_presence_breakdown(results),
        "compatible_records": len(records),
        "converted": sum(1 for r in results if r.converted),
        "acceptance_criterion": (
            "conversion_success_rate >= 0.95 sui record compatibili, "
            "source_field_preservation = 1.00 sui campi presenti all'origine, "
            "provenance_preservation = 1.00, unknown_field_honesty = 1.00"
        ),
    }


def meets_acceptance(evaluation: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Verifica i quattro criteri. Restituisce anche quali non sono soddisfatti."""
    thresholds = {
        "conversion_success_rate": 0.95,
        "source_field_preservation": 1.0,
        "provenance_preservation": 1.0,
        "unknown_field_honesty": 1.0,
    }
    failures: list[str] = []
    for name, minimum in thresholds.items():
        value = evaluation["measures"][name]["value"]
        if value is None:
            failures.append(f"{name}: non misurata")
        elif value < minimum:
            failures.append(f"{name} = {value:.4f} sotto {minimum}")
    return (not failures, failures)
