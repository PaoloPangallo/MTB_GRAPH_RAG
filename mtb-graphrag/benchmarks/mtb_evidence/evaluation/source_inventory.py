"""Inventario delle fonti citate dai 147 EvidenceStatement congelati.

L'universo di selezione e' definito **dagli statement**, non dal clinical gold.
E' la differenza fra chiedersi «quali fonti servono a far funzionare il sistema»
e «quali fonti il sistema ha effettivamente in mano»: solo la seconda domanda
produce un corpus che puo' smentire il sistema.

L'inventario e' una funzione pura degli artefatti congelati. Gli stessi input
producono lo stesso file, byte per byte.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence.source_identity import (
    DOI,
    NCT,
    PMID,
    SourceIdentifier,
    SourceIdentity,
    SourceIdentityResolver,
    identifiers_from_source_reference,
    identifiers_from_trial_reference,
)

INVENTORY_VERSION = "source_inventory/1.0"

# Stati di presenza nello snapshot, cosi' come l'audit del grafo li ha stabiliti.
PRESENCE_NODE = "node"
PRESENCE_CITATION_ONLY = "citation_only"
PRESENCE_ABSENT = "absent"
PRESENCE_UNKNOWN = "unknown"

# Strati di copertura. Non sono filtri di inclusione: servono a verificare che il
# corpus contenga anche cio' che al sistema fa comodo non avere.
STRATUM_RETRIEVED_IN_PILOT = "retrieved_in_pilot"
STRATUM_CITED_IN_REPORT = "cited_in_report"
STRATUM_REPORTED_THERAPY = "reported_therapy"
# Una citazione del report che il retrieval congelato di quel caso non aveva
# fornito. E' il segnale di falso positivo terapeutico piu' forte ottenibile
# **senza** il clinical gold, e va tenuto separato per questo: usare il gold per
# selezionare le fonti da annotare renderebbe il corpus circolare.
STRATUM_UNSUPPORTED_REPORT_CITATION = "unsupported_report_citation"
STRATUM_SENSITIVITY = "sensitivity"
STRATUM_RESISTANCE = "resistance"
STRATUM_NEGATIVE_POLARITY = "negative_polarity"
STRATUM_NON_THERAPEUTIC = "non_therapeutic_scope"
STRATUM_DISEASE_CONFLICT = "known_disease_conflict"
STRATUM_MULTI_STATEMENT = "multi_statement"
STRATUM_MULTI_INTERVENTION = "multi_intervention"
STRATUM_MULTI_DISEASE = "multi_disease"
STRATUM_DOI_IDENTIFIED = "doi_identified"
STRATUM_TRIAL_IDENTIFIED = "trial_identified"
STRATUM_PRESENT_AS_NODE = "present_as_node"
STRATUM_CITATION_ONLY = "citation_only"
STRATUM_PRESENCE_UNKNOWN = "presence_unknown"
STRATUM_HAS_REVIEWED_PROFILE = "has_reviewed_profile"

ALL_STRATA = (
    STRATUM_RETRIEVED_IN_PILOT,
    STRATUM_CITED_IN_REPORT,
    STRATUM_REPORTED_THERAPY,
    STRATUM_UNSUPPORTED_REPORT_CITATION,
    STRATUM_SENSITIVITY,
    STRATUM_RESISTANCE,
    STRATUM_NEGATIVE_POLARITY,
    STRATUM_NON_THERAPEUTIC,
    STRATUM_DISEASE_CONFLICT,
    STRATUM_MULTI_STATEMENT,
    STRATUM_MULTI_INTERVENTION,
    STRATUM_MULTI_DISEASE,
    STRATUM_DOI_IDENTIFIED,
    STRATUM_TRIAL_IDENTIFIED,
    STRATUM_PRESENT_AS_NODE,
    STRATUM_CITATION_ONLY,
    STRATUM_PRESENCE_UNKNOWN,
    STRATUM_HAS_REVIEWED_PROFILE,
)

PROFILE_ABSENT = "no_profile"
PROFILE_REVIEWED = "reviewed_profile"


@dataclass
class SourceInventoryEntry:
    """Una fonte e tutto cio' che gli statement congelati dicono di lei."""

    identity: SourceIdentity
    statement_ids: tuple[str, ...] = ()
    graph_evidence_ids: tuple[str, ...] = ()
    cases: tuple[str, ...] = ()
    diseases: tuple[str, ...] = ()
    biomarkers: tuple[str, ...] = ()
    interventions: tuple[str, ...] = ()
    directions: tuple[str, ...] = ()
    evidence_scopes: tuple[str, ...] = ()
    assertion_polarities: tuple[str, ...] = ()
    evidence_levels: tuple[str, ...] = ()
    presence_in_snapshot: str = PRESENCE_UNKNOWN
    presence_values: tuple[str, ...] = ()
    title: str = ""
    title_provenance: str = ""
    profile_status: str = PROFILE_ABSENT
    profile_ids: tuple[str, ...] = ()
    strata: tuple[str, ...] = ()
    requires_cohort_split: bool = False
    cohort_split_reason: str = ""
    annotation_priority: int = 3
    priority_reason: str = ""

    @property
    def canonical_source_id(self) -> str:
        return self.identity.canonical_source_id

    @property
    def statement_count(self) -> int:
        return len(self.statement_ids)

    def as_dict(self) -> dict[str, Any]:
        payload = self.identity.as_dict()
        payload.update(
            {
                "source_type": _source_type(self.identity),
                "title": self.title,
                "title_provenance": self.title_provenance,
                "statement_ids": list(self.statement_ids),
                "statement_count": self.statement_count,
                "graph_evidence_ids": list(self.graph_evidence_ids),
                "cases": list(self.cases),
                "diseases": list(self.diseases),
                "biomarkers": list(self.biomarkers),
                "interventions": list(self.interventions),
                "directions": list(self.directions),
                "evidence_scopes": list(self.evidence_scopes),
                "assertion_polarities": list(self.assertion_polarities),
                "evidence_levels": list(self.evidence_levels),
                "presence_in_snapshot": self.presence_in_snapshot,
                "presence_values": list(self.presence_values),
                "profile_status": self.profile_status,
                "profile_ids": list(self.profile_ids),
                "strata": list(self.strata),
                "requires_cohort_split": self.requires_cohort_split,
                "cohort_split_reason": self.cohort_split_reason,
                "annotation_priority": self.annotation_priority,
                "priority_reason": self.priority_reason,
                "inventory_version": INVENTORY_VERSION,
            }
        )
        return payload


def _source_type(identity: SourceIdentity) -> str:
    if identity.pmids:
        return PMID
    if identity.dois:
        return DOI
    if identity.ncts:
        return NCT
    return "unresolved"


def _label(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("label") or "")
    return "" if value is None else str(value)


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _resolve_presence(values: Sequence[str]) -> str:
    """Un solo stato per fonte, scelto in modo conservativo.

    Se un riferimento dice `node` la fonte esiste nel grafo come nodo, e vince su
    tutto: e' un fatto verificato. Fra `citation_only` e `unknown` vince
    `citation_only`, per lo stesso motivo. `absent` sopravvive solo se nessun
    riferimento afferma una presenza piu' forte, perche' affermare l'assenza
    quando qualcosa e' presente sarebbe l'errore piu' grave dei quattro.
    """
    unique = set(values)
    for candidate in (PRESENCE_NODE, PRESENCE_CITATION_ONLY, PRESENCE_ABSENT):
        if candidate in unique:
            return candidate
    return PRESENCE_UNKNOWN


def _cases_by_evidence_id(audit_dir: Path) -> dict[str, tuple[str, ...]]:
    """Mappa `evidence:<id>` → casi dell'audit in cui il record compare."""
    from benchmarks.mtb_evidence.pilot.audit_lib.serialize import read_jsonl

    mapping: dict[str, set[str]] = defaultdict(set)
    if not audit_dir.is_dir():
        return {}
    for case_dir in sorted(p for p in audit_dir.iterdir() if p.is_dir()):
        raw = case_dir / "raw_records.jsonl"
        if not raw.is_file():
            continue
        for row in read_jsonl(raw):
            record = row.get("record") if isinstance(row, dict) else None
            if not isinstance(record, dict):
                continue
            evidence_id = record.get("evidence_id")
            if evidence_id is not None:
                mapping[f"evidence:{evidence_id}"].add(case_dir.name)
    return {key: tuple(sorted(value)) for key, value in mapping.items()}


def _retrieved_record_ids(manifest_path: Path) -> set[str]:
    """Record entrati nel retrieval congelato del pilot."""
    import json

    if not manifest_path.is_file():
        return set()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    retrieved: set[str] = set()
    for case in (payload.get("frozen_retrieval") or {}).values():
        for record_id in case.get("record_ids") or []:
            retrieved.add(str(record_id))
    return retrieved


def _retrieved_pmids_by_case(manifest_path: Path) -> dict[str, set[str]]:
    import json

    from backend.pipeline.evidence._normalize import normalize_pmid

    if not manifest_path.is_file():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    per_case: dict[str, set[str]] = {}
    for case_id, case in (payload.get("frozen_retrieval") or {}).items():
        per_case[case_id] = {
            normalize_pmid(pmid) for pmid in case.get("pmids") or [] if normalize_pmid(pmid)
        }
    return per_case


@dataclass(frozen=True)
class _ReportSignals:
    """Cosa i report del pilot hanno effettivamente citato e nominato."""

    cited_pmids: frozenset[str]
    mentioned_therapies: frozenset[str]
    unsupported_pmids: frozenset[str]


def _report_signals(runs_path: Path, retrieved_by_case: Mapping[str, set[str]]) -> _ReportSignals:
    """Legge i report prodotti dal pilot.

    Le terapie «emesse» sono quelle che il report nomina, non quelle che il
    retrieval aveva a disposizione: sono insiemi molto diversi, e confonderli
    marcherebbe come «riportata» quasi ogni fonte del corpus.
    """
    import json

    from backend.pipeline.evidence._normalize import normalize_drug, normalize_pmid

    cited: set[str] = set()
    therapies: set[str] = set()
    unsupported: set[str] = set()
    if not runs_path.is_file():
        return _ReportSignals(frozenset(), frozenset(), frozenset())

    for line in runs_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        run = json.loads(stripped)
        report = run.get("report") or {}
        case_id = str(run.get("case_id") or "")
        available = retrieved_by_case.get(case_id, set())
        for pmid in report.get("cited_pmids") or []:
            normalized = normalize_pmid(pmid)
            if not normalized:
                continue
            cited.add(normalized)
            if available and normalized not in available:
                unsupported.add(normalized)
        for therapy in report.get("mentioned_therapies") or []:
            normalized_drug = normalize_drug(therapy)
            if normalized_drug:
                therapies.add(normalized_drug)
    return _ReportSignals(frozenset(cited), frozenset(therapies), frozenset(unsupported))


def _known_conflict_statements(conflicts_path: Path) -> set[str]:
    import json

    if not conflicts_path.is_file():
        return set()
    found: set[str] = set()
    for line in conflicts_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            found.add(str(json.loads(stripped).get("statement_id") or ""))
    found.discard("")
    return found


def _priority(strata: Sequence[str], profile_status: str) -> tuple[int, str]:
    """Priorita' di annotazione, non di inclusione.

    Ogni fonte e' comunque nello scope: la priorita' dice soltanto in che ordine
    conviene annotarla se la capacita' di revisione umana e' limitata. Nessuno
    strato abbassa la priorita' perche' la fonte «non serve».
    """
    strata_set = set(strata)
    if profile_status == PROFILE_REVIEWED:
        return 0, "profilo umano gia' disponibile: da riusare, non da riannotare"
    if STRATUM_UNSUPPORTED_REPORT_CITATION in strata_set:
        return 1, "citata da un report senza essere nel retrieval congelato di quel caso"
    if STRATUM_DISEASE_CONFLICT in strata_set:
        return 1, "conflitto noto fra denominazione della fonte e dello statement"
    if STRATUM_CITED_IN_REPORT in strata_set or STRATUM_REPORTED_THERAPY in strata_set:
        return 1, "fonte o terapia effettivamente emessa nel report del pilot"
    if STRATUM_RETRIEVED_IN_PILOT in strata_set:
        return 1, "fonte entrata nel retrieval congelato del pilot"
    if STRATUM_NEGATIVE_POLARITY in strata_set or STRATUM_RESISTANCE in strata_set:
        return 2, "polarita' negativa o resistenza: casi in cui un filtro sbagliato costa di piu'"
    if STRATUM_MULTI_STATEMENT in strata_set:
        return 2, "una sola annotazione qualifica piu' statement"
    return 3, "fonte del corpus non coinvolta nel retrieval del pilot"


def build_inventory(
    statements: Sequence[Mapping[str, Any]],
    *,
    audit_dir: Path,
    ablation_manifest: Path,
    conflicts_path: Path,
    pilot_runs: Path | None = None,
    profiles: Any = None,
) -> list[SourceInventoryEntry]:
    """Costruisce l'inventario completo delle fonti dei `statements`."""
    resolver = SourceIdentityResolver()
    per_group: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "statement_ids": set(),
            "graph_evidence_ids": set(),
            "diseases": set(),
            "biomarkers": set(),
            "interventions": set(),
            "directions": set(),
            "scopes": set(),
            "polarities": set(),
            "levels": set(),
            "presence": [],
            "titles": set(),
        }
    )

    # Prima passata: si popolano i gruppi. L'id restituito da `add` non viene
    # conservato, perche' un inserimento successivo puo' fondere due gruppi e
    # renderlo stale; si tiene invece una chiave di identificatore, che resta
    # valida perche' punta sempre al gruppo che la contiene.
    pending: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for statement in statements:
        references = list(statement.get("source_references") or [])
        trials = list(statement.get("trial_references") or [])
        tagged = [(reference, False) for reference in references]
        tagged += [(reference, True) for reference in trials]
        for reference, is_trial in tagged:
            identifiers = (
                identifiers_from_trial_reference(reference)
                if is_trial
                else identifiers_from_source_reference(reference)
            )
            valid = [item for item in identifiers if item.valid]
            if not valid:
                continue
            resolver.add(
                identifiers=identifiers,
                title=str(reference.get("title") or ""),
                provenance="evidence_statement",
            )
            pending.append((valid[0].key, statement, reference))

    # Seconda passata: ora la struttura dei gruppi e' definitiva.
    for representative_key, statement, reference in pending:
        group_id = resolver.group_id_of_key(representative_key)
        if not group_id:
            continue
        statement_id = str(statement.get("evidence_statement_id") or "")
        record_ids = list((statement.get("provenance") or {}).get("graph_record_ids") or [])
        title = str(reference.get("title") or "")
        bucket = per_group[group_id]
        bucket["statement_ids"].add(statement_id)
        bucket["graph_evidence_ids"].update(str(item) for item in record_ids)
        bucket["diseases"].add(_label(statement.get("disease")))
        bucket["biomarkers"].add(_label(statement.get("biomarker")))
        bucket["interventions"].add(_label(statement.get("intervention")))
        bucket["directions"].add(str(statement.get("direction") or ""))
        bucket["scopes"].add(str(statement.get("evidence_scope") or ""))
        bucket["polarities"].add(str(statement.get("assertion_polarity") or ""))
        level = statement.get("evidence_level") or {}
        bucket["levels"].add(str(level.get("original_value") or ""))
        bucket["presence"].append(str(reference.get("presence_in_snapshot") or PRESENCE_UNKNOWN))
        if title:
            bucket["titles"].add(title)

    cases_by_evidence = _cases_by_evidence_id(audit_dir)
    retrieved = _retrieved_record_ids(ablation_manifest)
    retrieved_pmids = _retrieved_pmids_by_case(ablation_manifest)
    signals = (
        _report_signals(pilot_runs, retrieved_pmids)
        if pilot_runs is not None
        else _ReportSignals(frozenset(), frozenset(), frozenset())
    )
    conflicted = _known_conflict_statements(conflicts_path)

    from backend.pipeline.evidence._normalize import normalize_drug

    profile_by_key: dict[str, Any] = {}
    if profiles is not None:
        from backend.pipeline.evidence.source_identity import identifiers_from_profile

        for profile in profiles:
            for identifier in identifiers_from_profile(profile):
                if identifier.valid:
                    profile_by_key[identifier.key] = profile

    entries: list[SourceInventoryEntry] = []
    by_group_id = {
        resolver.group_id_of_key(identity.keys[0]): identity
        for identity in resolver.identities()
        if identity.keys
    }
    for group_id, bucket in per_group.items():
        identity = by_group_id[group_id]
        graph_ids = _sorted_unique(bucket["graph_evidence_ids"])
        cases = _sorted_unique(
            case for record_id in graph_ids for case in cases_by_evidence.get(record_id, ())
        )
        presence = _resolve_presence(bucket["presence"])
        interventions = _sorted_unique(bucket["interventions"])
        diseases = _sorted_unique(bucket["diseases"])
        statement_ids = _sorted_unique(bucket["statement_ids"])

        matched_profiles = _sorted_unique(
            getattr(profile_by_key[key], "source_id", "")
            for key in identity.keys
            if key in profile_by_key
        )
        profile_status = PROFILE_REVIEWED if matched_profiles else PROFILE_ABSENT

        strata: set[str] = set()
        if any(record_id in retrieved for record_id in graph_ids):
            strata.add(STRATUM_RETRIEVED_IN_PILOT)
        if set(identity.pmids) & signals.cited_pmids:
            strata.add(STRATUM_CITED_IN_REPORT)
        if set(identity.pmids) & signals.unsupported_pmids:
            strata.add(STRATUM_UNSUPPORTED_REPORT_CITATION)
        if any(normalize_drug(name) in signals.mentioned_therapies for name in interventions):
            strata.add(STRATUM_REPORTED_THERAPY)
        if "sensitivity" in bucket["directions"]:
            strata.add(STRATUM_SENSITIVITY)
        if "resistance" in bucket["directions"]:
            strata.add(STRATUM_RESISTANCE)
        if "does_not_support" in bucket["polarities"]:
            strata.add(STRATUM_NEGATIVE_POLARITY)
        if bucket["scopes"] - {"therapeutic"}:
            strata.add(STRATUM_NON_THERAPEUTIC)
        if statement_ids and set(statement_ids) & conflicted:
            strata.add(STRATUM_DISEASE_CONFLICT)
        if len(statement_ids) > 1:
            strata.add(STRATUM_MULTI_STATEMENT)
        if len(interventions) > 1:
            strata.add(STRATUM_MULTI_INTERVENTION)
        if len(diseases) > 1:
            strata.add(STRATUM_MULTI_DISEASE)
        if identity.dois:
            strata.add(STRATUM_DOI_IDENTIFIED)
        if identity.ncts:
            strata.add(STRATUM_TRIAL_IDENTIFIED)
        if presence == PRESENCE_NODE:
            strata.add(STRATUM_PRESENT_AS_NODE)
        elif presence == PRESENCE_CITATION_ONLY:
            strata.add(STRATUM_CITATION_ONLY)
        elif presence == PRESENCE_UNKNOWN:
            strata.add(STRATUM_PRESENCE_UNKNOWN)
        if profile_status == PROFILE_REVIEWED:
            strata.add(STRATUM_HAS_REVIEWED_PROFILE)

        # Una fonte che copre piu' interventi o piu' malattie *puo'* descrivere
        # piu' coorti. L'inventario segnala il sospetto; solo la lettura della
        # fonte primaria puo' confermarlo, e non viene fatta qui.
        requires_split = len(interventions) > 1 or len(diseases) > 1
        split_reason = ""
        if requires_split:
            reasons = []
            if len(interventions) > 1:
                reasons.append(f"{len(interventions)} interventi distinti negli statement")
            if len(diseases) > 1:
                reasons.append(f"{len(diseases)} denominazioni di malattia distinte")
            split_reason = "; ".join(reasons)

        ordered_strata = tuple(item for item in ALL_STRATA if item in strata)
        priority, priority_reason = _priority(ordered_strata, profile_status)

        titles = sorted(bucket["titles"])
        entries.append(
            SourceInventoryEntry(
                identity=identity,
                statement_ids=statement_ids,
                graph_evidence_ids=graph_ids,
                cases=cases,
                diseases=diseases,
                biomarkers=_sorted_unique(bucket["biomarkers"]),
                interventions=interventions,
                directions=_sorted_unique(bucket["directions"]),
                evidence_scopes=_sorted_unique(bucket["scopes"]),
                assertion_polarities=_sorted_unique(bucket["polarities"]),
                evidence_levels=_sorted_unique(bucket["levels"]),
                presence_in_snapshot=presence,
                presence_values=_sorted_unique(bucket["presence"]),
                title=titles[0] if titles else "",
                title_provenance="evidence_statement" if titles else "",
                profile_status=profile_status,
                profile_ids=matched_profiles,
                strata=ordered_strata,
                requires_cohort_split=requires_split,
                cohort_split_reason=split_reason,
                annotation_priority=priority,
                priority_reason=priority_reason,
            )
        )

    entries.sort(key=lambda entry: entry.canonical_source_id)
    return entries


def apply_metadata(
    entries: Sequence[SourceInventoryEntry], metadata: Mapping[str, Mapping[str, Any]]
) -> None:
    """Completa i titoli con i metadati del registro, senza toccare altro.

    I metadati vengono da un registro ufficiale e sono conservati in cache; qui
    riempiono solo `title`, che nell'inventario ha un ruolo diagnostico. Nessun
    campo clinico viene derivato dal titolo.
    """
    for entry in entries:
        if entry.title:
            continue
        for key in entry.identity.keys:
            record = metadata.get(key)
            if record and record.get("title"):
                entry.title = str(record["title"])
                entry.title_provenance = str(record.get("retrieved_from") or "registry")
                break


def stratum_counts(entries: Sequence[SourceInventoryEntry]) -> dict[str, int]:
    counts = {stratum: 0 for stratum in ALL_STRATA}
    for entry in entries:
        for stratum in entry.strata:
            counts[stratum] += 1
    return counts
