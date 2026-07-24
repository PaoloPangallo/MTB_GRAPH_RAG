"""Rigenerazione versionata del qualification corpus.

Il corpus della V3 e' stato scritto una volta e poi corretto sette volte, ognuna
in una directory propria: curazione, audit strutturale, batch clinico/preclinico,
prima revisione, tre approvazioni, normalizzazione della politica. Ogni fase ha
fatto la cosa giusta — non riscrivere cio' che l'aveva preceduta — e il risultato
e' che **nessun file contiene lo stato corrente**. Per sapere che cosa vale oggi
di una unita' bisogna leggere otto artefatti e conoscerne l'ordine.

Questo modulo rende quell'ordine esplicito e eseguibile. Tre cose che tiene
separate perche' collassarle produrrebbe un corpus plausibile e falso:

- **precedenza non e' ricorrenza.** Prendere l'ultima occorrenza di una unita' fra
  otto file dipenderebbe dall'ordine di lettura. La precedenza e' dichiarata, il
  merge e' per campo, e ogni campo registra quale artefatto ha prevalso.
- **migrazione non e' copia.** I flag di propagazione non vengono trasportati:
  vengono ricalcolati dalla politica. Un flag serializzato che il codice non onora
  piu' e' un dato vecchio, e trasportarlo lo farebbe sembrare una decisione.
- **rigenerare non e' promuovere.** Una proposta resta una proposta, una revisione
  non indipendente resta non indipendente. La rigenerazione cambia dove le cose
  sono scritte, mai che cosa dicono.

Il fingerprint del grafo congelato non e' toccato: nessun dato viene scritto nel
KG, e il corpus rigenerato ne cita l'impronta invece di sostituirla.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .corpus_manifest import content_hash
from .profile_unit import (
    COHORT_RESOLVED,
    COHORT_SINGLE,
    MACHINE_EXTRACTED,
    UNIT_DIMENSIONS,
)
from .propagation_policy import FINAL, NONE, PROTOTYPE_ONLY, eligibility_for

REGENERATION_VERSION = "corpus_regeneration/1.0"

# --- stato della rigenerazione ------------------------------------------------
DRAFT = "draft"
VALIDATED = "validated"
READY_FOR_PROTOTYPE = "ready_for_prototype"
BLOCKED = "blocked"
FROZEN = "frozen"

REGENERATION_STATUSES = (DRAFT, VALIDATED, READY_FOR_PROTOTYPE, BLOCKED, FROZEN)

# --- classificazione delle differenze -----------------------------------------
EXPECTED_POLICY_MIGRATION = "expected_policy_migration"
EXPECTED_AUTHOR_APPROVAL = "expected_author_approval"
EXPECTED_UNIT_RESTRUCTURE = "expected_unit_restructure"
EXPECTED_HISTORY_UPDATE = "expected_history_update"
EXPECTED_HASH_CHANGE = "expected_hash_change"
UNEXPECTED_CHANGE = "unexpected_change"
UNRESOLVED_CONFLICT = "unresolved_conflict"

CHANGE_CLASSES = (
    EXPECTED_POLICY_MIGRATION,
    EXPECTED_AUTHOR_APPROVAL,
    EXPECTED_UNIT_RESTRUCTURE,
    EXPECTED_HISTORY_UPDATE,
    EXPECTED_HASH_CHANGE,
    UNEXPECTED_CHANGE,
    UNRESOLVED_CONFLICT,
)

# I campi che la politica calcola. Non vengono mai trasportati da un artefatto
# all'altro: se un record di ingresso li porta, il valore viene scartato e la
# discrepanza registrata. E' la differenza fra migrare e copiare.
DERIVED_POLICY_FIELDS = (
    "cohort_is_resolved",
    "propagation_eligibility",
    "may_display_qualifiers",
    "is_propagatable",
    "is_hard_filterable",
    "is_evaluable",
    "requires_second_independent_review",
)

# Campi che descrivono **l'esecuzione** e non i dati, e che quindi non
# partecipano all'hash. Includerli renderebbe ogni rigenerazione diversa dalla
# precedente per motivi che non riguardano il contenuto — e nel caso di
# `reverse_input_order` renderebbe l'impronta dipendente dall'ordine di lettura,
# che e' esattamente la proprieta' che la rigenerazione esiste per escludere.
NON_HASHED_FIELDS = (
    "generated_at",
    "created_at",
    "reviewed_at",
    "access_date",
    "review_date",
    "reverse_input_order",
)


# --- errori tipizzati ---------------------------------------------------------


class RegenerationError(RuntimeError):
    """La rigenerazione viola un invariante del corpus."""

    rule_id = "corpus_regeneration"


class UnresolvedMergeConflict(RegenerationError):
    """Due artefatti pari-ordinati propongono valori diversi per lo stesso campo."""

    rule_id = "unresolved_merge_conflict"


class DuplicateActiveIdentityError(RegenerationError):
    """Due unita' attive descrivono la stessa identita' semantica."""

    rule_id = "duplicate_active_identity"


class SupersededUnitActiveError(RegenerationError):
    """Una parent sostituita, o una proposta respinta, risulta attiva."""

    rule_id = "superseded_unit_is_active"


class StaleSerializedFlagError(RegenerationError):
    """Un flag di propagazione e' stato trasportato invece che ricalcolato."""

    rule_id = "stale_serialized_flag"


class UnauthorizedFinalError(RegenerationError):
    """Una unita' e' dichiarata `final` senza i prerequisiti."""

    rule_id = "final_without_prerequisites"


class HardFilterWithoutFinalError(RegenerationError):
    """Un qualificatore non definitivo e' dichiarato hard-filterable."""

    rule_id = "hard_filter_without_final"


class GoldEvaluableError(RegenerationError):
    """Il gold e' dichiarato valutabile senza seconda revisione o adjudication."""

    rule_id = "gold_evaluable_without_second_review"


class MissingProvenanceError(RegenerationError):
    """Un qualificatore noto e' privo di provenienza."""

    rule_id = "qualifier_without_provenance"


class AbstractOnlyFullTextClaimError(RegenerationError):
    """Una unita' abstract-only si dichiara verificata sul full text."""

    rule_id = "abstract_only_claims_full_text"


class NotSeparableCollapseError(RegenerationError):
    """Un `not_separable` e' stato convertito in un valore concreto."""

    rule_id = "not_separable_collapsed"


class NegativeResultInversionError(RegenerationError):
    """Un risultato negativo e' diventato un supporto positivo."""

    rule_id = "negative_result_inverted"


class CaseLevelGeneralizedError(RegenerationError):
    """Una evidenza su singoli pazienti e' stata estesa alla coorte."""

    rule_id = "case_level_generalized"


class UnverifiedMappingPromotedError(RegenerationError):
    """Un mapping non verificato e' stato promosso a sinonimo."""

    rule_id = "unverified_mapping_promoted"


class SnapshotFingerprintChangedError(RegenerationError):
    """L'impronta del grafo congelato e' cambiata: il KG non va toccato."""

    rule_id = "frozen_kg_fingerprint_changed"


class BlindingViolationError(RegenerationError):
    """Un packet cieco della seconda revisione e' cambiato."""

    rule_id = "second_review_packet_changed"


# =============================================================================
# Precedenza e merge field-level
# =============================================================================


@dataclass(frozen=True)
class SourceLayer:
    """Uno strato di artefatti, con la sua posizione nella precedenza.

    `rank` cresce con l'autorita': uno strato piu' alto sovrascrive i campi che
    dichiara, e **soltanto quelli**. I campi che non nomina restano dello strato
    sottostante — perche' una revisione che decide sul disegno dello studio non
    sta dicendo nulla sulla malattia, e trattare il suo silenzio come una
    cancellazione perderebbe dati che nessuno ha messo in discussione.
    """

    layer_id: str
    rank: int
    artifact: str
    kind: str = "profile_unit"
    artifact_hash: str = ""
    change_class: str = EXPECTED_AUTHOR_APPROVAL


@dataclass
class FieldDecision:
    """Quale strato ha fissato un campo, e quali strati sono stati scavalcati."""

    field_name: str
    value: Any
    selected_layer: str
    overridden_layers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "selected_layer": self.selected_layer,
            "overridden_layers": list(self.overridden_layers),
        }


@dataclass
class MergeResult:
    """Il record canonico di una entita', con l'audit di come e' stato ottenuto."""

    entity_id: str
    record: dict[str, Any]
    decisions: list[FieldDecision] = field(default_factory=list)
    candidate_layers: tuple[str, ...] = ()
    selected_layer: str = ""
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    def audit_row(self, *, rationale: str, artifact_hashes: Mapping[str, str]) -> dict[str, Any]:
        overridden = sorted(
            {
                decision.field_name
                for decision in self.decisions
                if decision.overridden_layers
            }
        )
        preserved = sorted(
            {
                decision.field_name
                for decision in self.decisions
                if not decision.overridden_layers
            }
        )
        return {
            "entity_id": self.entity_id,
            "candidate_sources": list(self.candidate_layers),
            "selected_source": self.selected_layer,
            "overridden_fields": overridden,
            "preserved_fields": preserved,
            "field_decisions": [decision.as_dict() for decision in self.decisions],
            "conflict_status": UNRESOLVED_CONFLICT if self.conflicts else "resolved",
            "conflicts": list(self.conflicts),
            "rationale": rationale,
            "source_artifact_hashes": {
                layer: artifact_hashes.get(layer, "") for layer in self.candidate_layers
            },
            "regeneration_version": REGENERATION_VERSION,
        }


def merge_records(
    entity_id: str,
    contributions: Sequence[tuple[SourceLayer, Mapping[str, Any]]],
    *,
    ignored_fields: Iterable[str] = DERIVED_POLICY_FIELDS,
) -> MergeResult:
    """Fonde i contributi di piu' strati campo per campo, in ordine di autorita'.

    Due strati **allo stesso rank** che propongono valori diversi non vengono
    risolti da una regola: la scelta fra due artefatti pari-ordinati e' un giudizio,
    e inventarne uno qui lo renderebbe invisibile. Il conflitto viene registrato e
    fa fallire la rigenerazione.

    I campi calcolati dalla politica sono esclusi dal merge: arrivano dopo, dal
    ricalcolo, e trasportarli qui li farebbe sembrare decisi da un revisore.
    """
    skipped = set(ignored_fields)
    ordered = sorted(contributions, key=lambda item: (item[0].rank, item[0].layer_id))

    record: dict[str, Any] = {}
    chosen: dict[str, tuple[SourceLayer, list[str]]] = {}
    conflicts: list[dict[str, Any]] = []

    for layer, payload in ordered:
        for key, value in payload.items():
            if key in skipped:
                continue
            if key not in chosen:
                record[key] = value
                chosen[key] = (layer, [])
                continue
            previous_layer, overridden = chosen[key]
            if previous_layer.rank == layer.rank and record[key] != value:
                conflicts.append(
                    {
                        "field_name": key,
                        "layers": sorted([previous_layer.layer_id, layer.layer_id]),
                        "values": [record[key], value],
                        "reason": (
                            "due artefatti pari-ordinati propongono valori diversi: la "
                            "scelta fra fonti di pari autorita' e' un giudizio umano"
                        ),
                    }
                )
                continue
            if layer.rank > previous_layer.rank:
                if record[key] != value:
                    overridden = overridden + [previous_layer.layer_id]
                record[key] = value
                chosen[key] = (layer, overridden)

    decisions = [
        FieldDecision(
            field_name=key,
            value=record[key],
            selected_layer=layer.layer_id,
            overridden_layers=tuple(overridden),
        )
        for key, (layer, overridden) in sorted(chosen.items())
    ]
    top = ordered[-1][0] if ordered else None
    return MergeResult(
        entity_id=entity_id,
        record=record,
        decisions=decisions,
        candidate_layers=tuple(layer.layer_id for layer, _ in ordered),
        selected_layer=top.layer_id if top else "",
        conflicts=conflicts,
    )


# =============================================================================
# Migrazione della politica di propagazione
# =============================================================================


@dataclass(frozen=True)
class PolicyMigration:
    """Il prima e il dopo di una unita', con la ragione del livello assegnato."""

    profile_unit_id: str
    before: Mapping[str, Any]
    after: Mapping[str, Any]
    reason: str
    stale_serialized_fields: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return any(
            self.before.get(key) != self.after.get(key)
            for key in DERIVED_POLICY_FIELDS
            if key in self.before
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_unit_id": self.profile_unit_id,
            "before": dict(self.before),
            "after": dict(self.after),
            "reason": self.reason,
            "stale_serialized_fields": list(self.stale_serialized_fields),
            "had_stale_serialized_flag": bool(self.stale_serialized_fields),
            "changed": self.changed,
            "change_class": EXPECTED_POLICY_MIGRATION,
            "regeneration_version": REGENERATION_VERSION,
        }


def migrate_policy(unit: Mapping[str, Any]) -> PolicyMigration:
    """Ricalcola i campi della politica per una unita', senza guardare i suoi flag.

    Il valore serializzato viene letto **solo** per dire se era obsoleto. Non
    entra nel calcolo: se lo facesse, un dato vecchio potrebbe sopravvivere a una
    migrazione che esiste per eliminarlo.
    """
    decision = eligibility_for(unit)
    cohort_state = str(unit.get("cohort_state") or COHORT_SINGLE)
    cohort_resolved = cohort_state in (COHORT_SINGLE, COHORT_RESOLVED)
    machine_extracted = str(unit.get("extraction_status") or "") == MACHINE_EXTRACTED

    after = {
        "cohort_is_resolved": cohort_resolved,
        "propagation_eligibility": decision.eligibility,
        # Una estrazione automatica puo' essere mostrata soltanto marcata come
        # tale: il contratto esistente non la nasconde, ma non le permette di
        # sembrare confermata.
        "may_display_qualifiers": decision.may_display_qualifiers,
        "is_propagatable": decision.is_propagatable and cohort_resolved,
        "is_hard_filterable": decision.may_hard_filter and cohort_resolved,
        "is_evaluable": decision.is_evaluable,
        "requires_second_independent_review": decision.requires_second_independent_review,
        "machine_extracted": machine_extracted,
    }
    before = {key: unit[key] for key in DERIVED_POLICY_FIELDS if key in unit}
    stale = tuple(
        sorted(key for key, value in before.items() if value != after.get(key))
    )
    return PolicyMigration(
        profile_unit_id=str(unit.get("profile_unit_id") or ""),
        before=before,
        after=after,
        reason=decision.reason,
        stale_serialized_fields=stale,
    )


def apply_policy(unit: Mapping[str, Any]) -> dict[str, Any]:
    """L'unita' con i campi della politica ricalcolati."""
    migration = migrate_policy(unit)
    record = {key: value for key, value in unit.items() if key not in DERIVED_POLICY_FIELDS}
    record.update(
        {key: value for key, value in migration.after.items() if key != "machine_extracted"}
    )
    return record


# =============================================================================
# Validatori
# =============================================================================


@dataclass(frozen=True)
class ValidationFinding:
    """Una violazione, con la regola e l'errore tipizzato che la rappresentano."""

    rule_id: str
    error_type: type[RegenerationError]
    subject: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "error_type": self.error_type.__name__,
            "subject": self.subject,
            "message": self.message,
        }

    def raise_it(self) -> None:
        raise self.error_type(self.message)


def _finding(
    error: type[RegenerationError], subject: str, message: str
) -> ValidationFinding:
    return ValidationFinding(error.rule_id, error, subject, message)


def semantic_identity(unit: Mapping[str, Any]) -> tuple[str, str]:
    """Che cosa rende due unita' la stessa unita': la fonte e la coorte.

    Non l'id: due id diversi che descrivono la stessa coorte della stessa fonte
    sono un duplicato, ed e' il caso che una rigenerazione da otto artefatti puo'
    produrre senza accorgersene.
    """
    return (
        str(unit.get("canonical_source_id") or ""),
        str(unit.get("cohort_id") or unit.get("profile_unit_id") or ""),
    )


def validate_active_units(units: Sequence[Mapping[str, Any]]) -> list[ValidationFinding]:
    """Le unita' attive: identita' unica, nessuna storica, nessuna respinta."""
    findings: list[ValidationFinding] = []
    seen: dict[tuple[str, str], str] = {}
    for unit in units:
        unit_id = str(unit.get("profile_unit_id") or "")
        identity = semantic_identity(unit)
        if identity in seen:
            findings.append(
                _finding(
                    DuplicateActiveIdentityError,
                    unit_id,
                    f"{unit_id} e {seen[identity]} descrivono la stessa coorte della "
                    f"stessa fonte {identity}: due unita' attive per una struttura sola",
                )
            )
        seen[identity] = unit_id

        if unit.get("superseded_by"):
            findings.append(
                _finding(
                    SupersededUnitActiveError,
                    unit_id,
                    f"{unit_id} e' attiva ma dichiara superseded_by "
                    f"{list(unit.get('superseded_by'))}: una unita' sostituita non e' evidenza corrente",
                )
            )
        if str(unit.get("review_status") or "").startswith("rejected"):
            findings.append(
                _finding(
                    SupersededUnitActiveError,
                    unit_id,
                    f"{unit_id} e' attiva con review_status {unit.get('review_status')!r}: "
                    "una proposta respinta non entra nelle viste correnti",
                )
            )
    return findings


def validate_policy_fields(units: Sequence[Mapping[str, Any]]) -> list[ValidationFinding]:
    """I flag sono quelli che la politica calcola oggi, non quelli di ieri."""
    findings: list[ValidationFinding] = []
    for unit in units:
        unit_id = str(unit.get("profile_unit_id") or "")
        expected = migrate_policy(unit).after
        for key in DERIVED_POLICY_FIELDS:
            if key in unit and unit[key] != expected[key]:
                findings.append(
                    _finding(
                        StaleSerializedFlagError,
                        unit_id,
                        f"{unit_id}.{key} vale {unit[key]!r} ma la politica calcola "
                        f"{expected[key]!r}: il flag e' stato trasportato, non migrato",
                    )
                )
        if unit.get("propagation_eligibility") == FINAL and not unit.get("is_propagatable"):
            findings.append(
                _finding(
                    UnauthorizedFinalError,
                    unit_id,
                    f"{unit_id} e' final ma non propagabile: il livello non corrisponde ai fatti",
                )
            )
        if unit.get("is_hard_filterable") and unit.get("propagation_eligibility") != FINAL:
            findings.append(
                _finding(
                    HardFilterWithoutFinalError,
                    unit_id,
                    f"{unit_id} e' hard-filterable con eligibility "
                    f"{unit.get('propagation_eligibility')!r}: un filtro sbagliato rimuove "
                    "cio' che nessuno potra' piu' vedere",
                )
            )
        if str(unit.get("extraction_status") or "") == MACHINE_EXTRACTED and unit.get(
            "is_hard_filterable"
        ):
            findings.append(
                _finding(
                    HardFilterWithoutFinalError,
                    unit_id,
                    f"{unit_id} e' machine_extracted e hard-filterable: nessuno ha letto la fonte",
                )
            )
    return findings


def validate_integrity(units: Sequence[Mapping[str, Any]]) -> list[ValidationFinding]:
    """Gli invarianti che non riguardano la politica ma il significato."""
    findings: list[ValidationFinding] = []
    for unit in units:
        unit_id = str(unit.get("profile_unit_id") or "")

        for dimension in unit.get("known_dimensions") or []:
            fields = {item.get("field_name") for item in unit.get("provenance") or []}
            if dimension not in fields:
                findings.append(
                    _finding(
                        MissingProvenanceError,
                        unit_id,
                        f"{unit_id}.{dimension} e' nota ma non ha provenienza: un valore "
                        "senza provenienza non e' distinguibile da un valore inventato",
                    )
                )

        if str(unit.get("source_basis") or "") == "abstract_only" and unit.get(
            "full_text_verified"
        ):
            findings.append(
                _finding(
                    AbstractOnlyFullTextClaimError,
                    unit_id,
                    f"{unit_id} e' abstract_only e dichiara full_text_verified",
                )
            )

        for key in ("preclinical_model_composition", "component_to_statement_mapping"):
            declared = unit.get(key)
            if declared is not None and declared not in ("not_separable", "unknown"):
                findings.append(
                    _finding(
                        NotSeparableCollapseError,
                        unit_id,
                        f"{unit_id}.{key} vale {declared!r}: un `not_separable` risolto in "
                        "un valore concreto afferma una struttura che la fonte non fornisce",
                    )
                )

        if unit.get("experiment_role") == "negative_experiment" and unit.get(
            "assertion_polarity"
        ) not in ("does_not_support", None):
            findings.append(
                _finding(
                    NegativeResultInversionError,
                    unit_id,
                    f"{unit_id} e' un esperimento negativo con polarita' "
                    f"{unit.get('assertion_polarity')!r}: il risultato e' stato invertito",
                )
            )
    return findings


def validate_decisions(decisions: Sequence[Mapping[str, Any]]) -> list[ValidationFinding]:
    """Le decisioni sugli statement: granularita' e mapping restano dove sono."""
    from .evidence_granularity import is_non_generalizable

    findings: list[ValidationFinding] = []
    for row in decisions:
        statement_id = str(row.get("statement_id") or "")
        if is_non_generalizable(row.get("evidence_granularity")):
            if row.get("cohort_generalizable"):
                findings.append(
                    _finding(
                        CaseLevelGeneralizedError,
                        statement_id,
                        f"{statement_id} e' {row.get('evidence_granularity')!r} e dichiara "
                        "cohort_generalizable: cio' che si e' visto in pochi diventerebbe "
                        "una proprieta' di tutti",
                    )
                )
            if str(row.get("frequency_inference") or "forbidden") != "forbidden":
                findings.append(
                    _finding(
                        CaseLevelGeneralizedError,
                        statement_id,
                        f"{statement_id} permette una inferenza di frequenza senza denominatore",
                    )
                )
    return findings


def validate_mappings(mappings: Sequence[Mapping[str, Any]]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for row in mappings:
        mapping_id = str(row.get("mapping_id") or row.get("source_term") or "")
        if row.get("promoted_to_verified_synonym") or row.get("mapping_status") in (
            "verified_synonym",
            "verified",
        ):
            findings.append(
                _finding(
                    UnverifiedMappingPromotedError,
                    mapping_id,
                    f"{mapping_id} e' stato promosso a sinonimo verificato: nessuna "
                    "verifica terminologica e' stata eseguita",
                )
            )
    return findings


def validate_gold(records: Sequence[Mapping[str, Any]]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for row in records:
        link_id = str(row.get("gold_link_id") or "")
        has_second = row.get("second_annotator") is not None
        adjudicated = row.get("adjudication") is not None
        if row.get("is_evaluable") and not (has_second or adjudicated):
            findings.append(
                _finding(
                    GoldEvaluableError,
                    link_id,
                    f"{link_id} e' valutabile senza seconda revisione ne' adjudication",
                )
            )
        annotation = row.get("first_review_annotation") or {}
        if annotation.get("candidate_status") and row.get("final_status") == annotation.get(
            "candidate_status"
        ):
            findings.append(
                _finding(
                    GoldEvaluableError,
                    link_id,
                    f"{link_id}: lo stato del candidato e' stato copiato in final_status",
                )
            )
    return findings


def validate_fingerprints(
    *,
    frozen_kg_before: str,
    frozen_kg_after: str,
    blind_packets_before: Mapping[str, str],
    blind_packets_after: Mapping[str, str],
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if frozen_kg_before != frozen_kg_after:
        findings.append(
            _finding(
                SnapshotFingerprintChangedError,
                "frozen_kg_snapshot_fingerprint",
                f"l'impronta del grafo congelato e' passata da {frozen_kg_before!r} a "
                f"{frozen_kg_after!r}: il KG non viene toccato da questa fase",
            )
        )
    changed = sorted(
        name
        for name in set(blind_packets_before) | set(blind_packets_after)
        if blind_packets_before.get(name) != blind_packets_after.get(name)
    )
    if changed:
        findings.append(
            _finding(
                BlindingViolationError,
                "second_review_packets",
                f"packet ciechi modificati: {changed}",
            )
        )
    return findings


def validate_corpus(
    *,
    active_units: Sequence[Mapping[str, Any]],
    all_units: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]] = (),
    mappings: Sequence[Mapping[str, Any]] = (),
    gold: Sequence[Mapping[str, Any]] = (),
    frozen_kg_before: str = "",
    frozen_kg_after: str = "",
    blind_packets_before: Mapping[str, str] | None = None,
    blind_packets_after: Mapping[str, str] | None = None,
) -> list[ValidationFinding]:
    """Tutti i validatori, in un elenco solo.

    Restituisce senza sollevare: chi chiama decide se una violazione blocca la
    rigenerazione o va soltanto registrata. Un corpus bloccato per sei motivi va
    sistemato una volta, non sei.
    """
    findings: list[ValidationFinding] = []
    findings.extend(validate_active_units(active_units))
    findings.extend(validate_policy_fields(all_units))
    findings.extend(validate_integrity(all_units))
    findings.extend(validate_decisions(decisions))
    findings.extend(validate_mappings(mappings))
    findings.extend(validate_gold(gold))
    findings.extend(
        validate_fingerprints(
            frozen_kg_before=frozen_kg_before,
            frozen_kg_after=frozen_kg_after,
            blind_packets_before=dict(blind_packets_before or {}),
            blind_packets_after=dict(blind_packets_after or {}),
        )
    )
    return findings


# =============================================================================
# Impronta del corpus
# =============================================================================


def strip_volatile(payload: Any) -> Any:
    """Copia senza i campi che cambiano a ogni esecuzione.

    Un timestamp dentro l'hash rende ogni rigenerazione diversa dalla precedente
    per un motivo che non riguarda i dati, e quindi rende l'hash inutile a dire se
    i dati sono cambiati.
    """
    if isinstance(payload, dict):
        return {
            key: strip_volatile(value)
            for key, value in payload.items()
            if key not in NON_HASHED_FIELDS
        }
    if isinstance(payload, (list, tuple)):
        return [strip_volatile(item) for item in payload]
    return payload


def stable_hash(payload: Any) -> str:
    """Hash del contenuto senza i campi volatili, indipendente dall'ordine di ingresso."""
    return content_hash(strip_volatile(payload))


def corpus_fingerprint(components: Mapping[str, str]) -> str:
    """Impronta canonica del qualification corpus.

    Deriva dagli hash dei componenti e **non** sostituisce l'impronta del grafo
    congelato: quella identifica il KG, questa identifica cio' che la revisione ne
    ha fatto. Chiamare la seconda «nuovo snapshot del KG» direbbe che il grafo e'
    cambiato, e il grafo non e' stato toccato.
    """
    return content_hash({key: components[key] for key in sorted(components)})


__all__ = [
    "REGENERATION_VERSION",
    "REGENERATION_STATUSES",
    "DRAFT",
    "VALIDATED",
    "READY_FOR_PROTOTYPE",
    "BLOCKED",
    "FROZEN",
    "CHANGE_CLASSES",
    "EXPECTED_POLICY_MIGRATION",
    "EXPECTED_AUTHOR_APPROVAL",
    "EXPECTED_UNIT_RESTRUCTURE",
    "EXPECTED_HISTORY_UPDATE",
    "EXPECTED_HASH_CHANGE",
    "UNEXPECTED_CHANGE",
    "UNRESOLVED_CONFLICT",
    "DERIVED_POLICY_FIELDS",
    "NON_HASHED_FIELDS",
    "RegenerationError",
    "UnresolvedMergeConflict",
    "DuplicateActiveIdentityError",
    "SupersededUnitActiveError",
    "StaleSerializedFlagError",
    "UnauthorizedFinalError",
    "HardFilterWithoutFinalError",
    "GoldEvaluableError",
    "MissingProvenanceError",
    "AbstractOnlyFullTextClaimError",
    "NotSeparableCollapseError",
    "NegativeResultInversionError",
    "CaseLevelGeneralizedError",
    "UnverifiedMappingPromotedError",
    "SnapshotFingerprintChangedError",
    "BlindingViolationError",
    "SourceLayer",
    "FieldDecision",
    "MergeResult",
    "PolicyMigration",
    "ValidationFinding",
    "merge_records",
    "migrate_policy",
    "apply_policy",
    "semantic_identity",
    "validate_active_units",
    "validate_policy_fields",
    "validate_integrity",
    "validate_decisions",
    "validate_mappings",
    "validate_gold",
    "validate_fingerprints",
    "validate_corpus",
    "strip_volatile",
    "stable_hash",
    "corpus_fingerprint",
]
