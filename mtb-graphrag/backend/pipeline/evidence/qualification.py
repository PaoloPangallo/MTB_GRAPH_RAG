"""Collegamento fra EvidenceStatement e SourceClinicalProfile, e vista qualificata.

Il punto centrale di questo modulo e' una cosa che sembra ovvia e non lo e':

> **un join per PMID non implica applicabilita'.**

Un `SourceClinicalProfile` descrive **lo studio**: popolazione, setting, linea di
terapia, criteri di inclusione. Uno `EvidenceStatement` descrive **una proposizione**
estratta da quello studio. Uno studio contiene tipicamente piu' proposizioni, e non
tutte riguardano la stessa coorte: un'analisi di sottogruppo, un braccio diverso o una
direzione opposta non ereditano automaticamente la linea di terapia del braccio
principale.

Per questo il link non copia i qualificatori dentro lo statement. Registra quali
dimensioni *potrebbero* essere aggiunte, quali no e perche', e lascia allo statement
base la sua identita' intatta.

La vista qualificata e' **derivata e read-only**. Non e' un nuovo EvidenceStatement
congelato, e non va confusa con l'applicabilita' al caso, che appartiene a una fase
successiva: qui si descrive l'evidenza, non la sua pertinenza a un paziente.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from ._normalize import diseases_match, normalize_drug, normalize_nct, normalize_pmid, normalize_text

LINK_VERSION = "qualification_link/1.0"

# Metodo con cui il link e' stato stabilito.
EXACT_PMID = "exact_pmid"
EXACT_DOI = "exact_doi"
EXACT_NCT = "exact_nct"
EXACT_CONTROLLED_IDENTIFIER = "exact_controlled_identifier"
COMPOSITE_SOURCE_MATCH = "composite_source_match"
MANUAL_LINK = "manual_link"
NO_MATCH = "no_match"

# Esito del confronto fra statement e profilo.
EXACT_SOURCE_MATCH = "exact_source_match"
MULTI_SOURCE_MATCH = "multi_source_match"
AMBIGUOUS_MATCH = "ambiguous_match"
CONFLICTING_MATCH = "conflicting_match"
NO_MATCH_STATUS = "no_match"
REQUIRES_HUMAN_REVIEW = "requires_human_review"

# Stato di qualificazione della vista.
UNQUALIFIED = "unqualified"
PARTIALLY_QUALIFIED = "partially_qualified"
QUALIFIED = "qualified"
AMBIGUOUS = "ambiguous"
CONFLICTING = "conflicting"
HUMAN_REVIEW_REQUIRED = "human_review_required"

# Dimensioni che il profilo puo' aggiungere. Sono esattamente quelle che il grafo V2
# non modella: e' la ragione per cui i profili esistono.
PROFILE_DIMENSIONS = (
    "disease_setting",
    "stage",
    "therapy_line",
    "resection_status",
    "population",
    "prior_therapies",
    "biomarker_requirements",
    "regimen",
    "inclusion_criteria_summary",
    "exclusion_criteria_summary",
)

# Mappa dimensione → attributo del SourceClinicalProfile.
_DIMENSION_ATTRIBUTE = {
    "disease_setting": "setting",
    "stage": "stage",
    "therapy_line": "therapy_line",
    "resection_status": None,  # non presente nel profilo: resta unknown
    "population": "population",
    "prior_therapies": "prior_therapies",
    "biomarker_requirements": "biomarker_requirements",
    "regimen": "regimen",
    "inclusion_criteria_summary": "inclusion_criteria_summary",
    "exclusion_criteria_summary": "exclusion_criteria_summary",
}

# Dimensioni su cui statement e profilo devono essere coerenti perche' il profilo possa
# qualificare lo statement. Una divergenza qui non e' un dettaglio: significa che il
# profilo descrive una popolazione diversa da quella della proposizione.
BLOCKING_DIMENSIONS = ("disease", "intervention")


from .propagation_policy import (  # noqa: E402
    FINAL,
    NONE,
    PROTOTYPE_ONLY,
    PrototypeHardFilterError,
    eligibility_for,
)


class QualificationLinkError(RuntimeError):
    """Il collegamento fra statement e profilo non e' costruibile."""


@dataclass(frozen=True)
class DimensionValue:
    """Un qualificatore con la sua origine completa."""

    dimension: str
    value: Any
    value_origin: str
    source_profile_id: str
    source_identifier: str
    qualification_link_id: str
    review_status: str
    # Che cosa si puo' fare con questo valore. Viaggia con il valore e non a
    # parte, perche' un qualificatore separato dal suo livello di autorizzazione
    # e' un qualificatore che qualcuno usera' per filtrare.
    propagation_eligibility: str = PROTOTYPE_ONLY

    @property
    def may_hard_filter(self) -> bool:
        return self.propagation_eligibility == FINAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "value_origin": self.value_origin,
            "source_profile_id": self.source_profile_id,
            "source_identifier": self.source_identifier,
            "qualification_link_id": self.qualification_link_id,
            "review_status": self.review_status,
            "propagation_eligibility": self.propagation_eligibility,
            "may_hard_filter": self.may_hard_filter,
        }


@dataclass(frozen=True)
class EvidenceQualificationLink:
    """Spiega il collegamento fra uno statement e un profilo, e i suoi limiti."""

    qualification_link_id: str
    statement_id: str
    source_profile_id: str
    match_method: str
    match_status: str
    statement_source_ids: tuple[str, ...] = ()
    profile_source_ids: tuple[str, ...] = ()
    matched_source_ids: tuple[str, ...] = ()
    applicable_profile_dimensions: tuple[str, ...] = ()
    excluded_profile_dimensions: tuple[str, ...] = ()
    added_dimensions: tuple[DimensionValue, ...] = ()
    conflicts: tuple[Mapping[str, Any], ...] = ()
    ambiguity_reasons: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    review_status: str = "machine_linked"
    link_version: str = LINK_VERSION
    created_at: str = ""

    @property
    def qualifies(self) -> bool:
        return self.match_status in {EXACT_SOURCE_MATCH, MULTI_SOURCE_MATCH}

    def as_dict(self) -> dict[str, Any]:
        return {
            "qualification_link_id": self.qualification_link_id,
            "link_version": self.link_version,
            "statement_id": self.statement_id,
            "source_profile_id": self.source_profile_id,
            "statement_source_ids": list(self.statement_source_ids),
            "profile_source_ids": list(self.profile_source_ids),
            "matched_source_ids": list(self.matched_source_ids),
            "match_method": self.match_method,
            "match_status": self.match_status,
            "applicable_profile_dimensions": list(self.applicable_profile_dimensions),
            "excluded_profile_dimensions": list(self.excluded_profile_dimensions),
            "added_dimensions": [d.as_dict() for d in self.added_dimensions],
            "conflicts": [dict(c) for c in self.conflicts],
            "ambiguity_reasons": list(self.ambiguity_reasons),
            "provenance": dict(self.provenance),
            "review_status": self.review_status,
            "created_at": self.created_at,
        }


def _statement_sources(statement: Mapping[str, Any]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"pubmed": [], "doi": [], "clinicaltrials_gov": [], "other": []}
    for reference in list(statement.get("source_references") or []) + list(
        statement.get("trial_references") or []
    ):
        kind = str(reference.get("source_type") or "other")
        identifier = str(reference.get("external_identifier") or "")
        if not identifier:
            continue
        buckets.setdefault(kind, []).append(identifier)
    return buckets


def _profile_sources(profile: Any) -> dict[str, list[str]]:
    pmid = normalize_pmid(getattr(profile, "pmid", ""))
    ncts = [normalize_nct(n) for n in getattr(profile, "nct_ids", ()) or ()]
    return {
        "pubmed": [pmid] if pmid else [],
        "clinicaltrials_gov": [n for n in ncts if n],
        "doi": [],
        "other": [],
    }


def _match_sources(statement: Mapping[str, Any], profile: Any) -> tuple[str, list[str]]:
    """Trova il metodo di match piu' specifico e gli identificatori condivisi.

    L'ordine di preferenza e' PMID, DOI, NCT. Nessun matching sul titolo entra in una
    decisione automatica: un titolo simile non e' la stessa fonte, e usarlo
    produrrebbe collegamenti che nessuno ha verificato.
    """
    statement_sources = _statement_sources(statement)
    profile_sources = _profile_sources(profile)

    for kind, method in (
        ("pubmed", EXACT_PMID),
        ("doi", EXACT_DOI),
        ("clinicaltrials_gov", EXACT_NCT),
    ):
        left = {normalize_pmid(v) if kind == "pubmed" else v.casefold()
                for v in statement_sources.get(kind, [])}
        right = {normalize_pmid(v) if kind == "pubmed" else v.casefold()
                 for v in profile_sources.get(kind, [])}
        shared = sorted(value for value in (left & right) if value)
        if shared:
            return method, shared
    return NO_MATCH, []


def _coherence_conflicts(
    statement: Mapping[str, Any], profile: Any
) -> list[dict[str, Any]]:
    """Divergenze sulle dimensioni bloccanti fra statement e profilo."""
    conflicts: list[dict[str, Any]] = []

    statement_disease = str((statement.get("disease") or {}).get("label") or "")
    profile_disease = str(getattr(profile, "disease", "") or "")
    if statement_disease and profile_disease and not diseases_match(
        statement_disease, profile_disease
    ):
        conflicts.append(
            {
                "dimension": "disease",
                "statement_value": statement_disease,
                "profile_value": profile_disease,
                "reason": "le due denominazioni non indicano la stessa entita'",
            }
        )

    statement_drug = normalize_drug((statement.get("intervention") or {}).get("label") or "")
    profile_drugs = {normalize_drug(item) for item in getattr(profile, "interventions", ()) or ()}
    if statement_drug and profile_drugs and statement_drug not in profile_drugs:
        conflicts.append(
            {
                "dimension": "intervention",
                "statement_value": statement_drug,
                "profile_value": sorted(profile_drugs),
                "reason": "l'intervento della proposizione non e' fra quelli dello studio",
            }
        )
    return conflicts


def _ambiguity_reasons(profile: Any) -> list[str]:
    """Situazioni in cui il profilo non identifica una coorte sola.

    Con piu' interventi non e' determinabile a quale braccio si riferiscano setting e
    linea di terapia, e applicarli allo statement sarebbe una scelta arbitraria.
    """
    reasons: list[str] = []
    interventions = [i for i in (getattr(profile, "interventions", ()) or ()) if i]
    if len(interventions) > 1:
        reasons.append(
            f"il profilo dichiara {len(interventions)} interventi: la coorte di "
            "riferimento dei qualificatori non e' determinabile"
        )
    if len(getattr(profile, "nct_ids", ()) or ()) > 1:
        reasons.append("il profilo referenzia piu' trial")
    return reasons


def build_link(
    statement: Mapping[str, Any],
    profile: Any,
    *,
    now: str | None = None,
) -> EvidenceQualificationLink:
    """Costruisce un link conservativo fra uno statement e un profilo.

    Non modifica ne' lo statement ne' il profilo. Le dimensioni vengono dichiarate
    applicabili solo se il match e' esatto, non ci sono conflitti bloccanti e il
    profilo identifica una coorte sola.
    """
    timestamp = now or datetime.now(timezone.utc).isoformat()
    statement_id = str(statement.get("evidence_statement_id") or "")
    profile_id = str(getattr(profile, "source_id", "") or "")
    link_id = f"QL-{statement_id}-{profile_id}"

    statement_sources = _statement_sources(statement)
    profile_sources = _profile_sources(profile)
    flat_statement = sorted({v for values in statement_sources.values() for v in values})
    flat_profile = sorted({v for values in profile_sources.values() for v in values})

    method, shared = _match_sources(statement, profile)
    conflicts = _coherence_conflicts(statement, profile) if shared else []
    ambiguity = _ambiguity_reasons(profile) if shared else []

    if not shared:
        status = NO_MATCH_STATUS
    elif conflicts:
        status = CONFLICTING_MATCH
    elif ambiguity:
        status = AMBIGUOUS_MATCH
    elif len(shared) > 1:
        status = MULTI_SOURCE_MATCH
    else:
        status = EXACT_SOURCE_MATCH

    # La politica di propagazione decide se il profilo puo' contribuire, e a
    # quale titolo. Un profilo mai revisionato non contribuisce affatto: i suoi
    # valori esistono ma non sono qualificatori di nessuno.
    decision = eligibility_for(
        {
            "profile_unit_id": profile_id,
            "review_status": str(getattr(profile, "review_status", "") or ""),
            "cohort_state": str(getattr(profile, "cohort_state", "single_cohort") or "single_cohort"),
            "independent_review": bool(getattr(profile, "independent_review", False)),
            "agreement_state": str(getattr(profile, "agreement_state", "") or ""),
        }
    )

    applicable: list[str] = []
    excluded: list[str] = []
    added: list[DimensionValue] = []

    for dimension in PROFILE_DIMENSIONS:
        attribute = _DIMENSION_ATTRIBUTE.get(dimension)
        value = getattr(profile, attribute, None) if attribute else None
        if value in (None, "", (), []):
            excluded.append(dimension)
            continue
        if status not in {EXACT_SOURCE_MATCH, MULTI_SOURCE_MATCH}:
            # Match ambiguo o conflittuale: la dimensione esiste ma non viene applicata.
            excluded.append(dimension)
            continue
        if decision.eligibility == NONE:
            # Nessuna revisione ha confermato il valore: non e' un qualificatore.
            excluded.append(dimension)
            continue
        applicable.append(dimension)
        added.append(
            DimensionValue(
                dimension=dimension,
                value=list(value) if isinstance(value, (list, tuple)) else value,
                value_origin="reviewed_source_profile",
                source_profile_id=profile_id,
                source_identifier=shared[0] if shared else "",
                qualification_link_id=link_id,
                review_status=str(getattr(profile, "review_status", "unknown")),
                propagation_eligibility=decision.eligibility,
            )
        )

    return EvidenceQualificationLink(
        qualification_link_id=link_id,
        statement_id=statement_id,
        source_profile_id=profile_id,
        match_method=method,
        match_status=status,
        statement_source_ids=tuple(flat_statement),
        profile_source_ids=tuple(flat_profile),
        matched_source_ids=tuple(shared),
        applicable_profile_dimensions=tuple(applicable),
        excluded_profile_dimensions=tuple(excluded),
        added_dimensions=tuple(added),
        conflicts=tuple(conflicts),
        ambiguity_reasons=tuple(ambiguity),
        provenance={
            "linker_version": LINK_VERSION,
            "statement_origin": (statement.get("provenance") or {}).get("origin"),
            "profile_origin": "reviewed_source_profile",
            "snapshot_fingerprint": (statement.get("provenance") or {}).get(
                "snapshot_fingerprint"
            ),
            "match_basis": "source identifier only; nessun matching sul titolo",
            "propagation_eligibility": decision.eligibility,
            "propagation_reason": decision.reason,
        },
        review_status="machine_linked",
        created_at=timestamp,
    )


def build_links(
    statements: Sequence[Mapping[str, Any]],
    profiles: Iterable[Any],
    *,
    now: str | None = None,
) -> list[EvidenceQualificationLink]:
    """Costruisce i link fra tutti gli statement e tutti i profili che li citano.

    Vengono restituiti solo i link con almeno una fonte condivisa: un link `no_match`
    fra ogni coppia produrrebbe rumore proporzionale al prodotto dei due insiemi.
    """
    profile_list = list(profiles)
    links: list[EvidenceQualificationLink] = []
    for statement in statements:
        for profile in profile_list:
            link = build_link(statement, profile, now=now)
            if link.match_status != NO_MATCH_STATUS:
                links.append(link)
    return sorted(links, key=lambda item: (item.statement_id, item.source_profile_id))


# ── Vista qualificata ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QualifiedEvidenceView:
    """Vista derivata e read-only: statement base piu' qualificatori con origine.

    Non e' un nuovo EvidenceStatement, non e' congelabile, e non descrive
    l'applicabilita' al caso — quella appartiene a una fase successiva. Qui si descrive
    l'evidenza con i qualificatori che le fonti revisionate permettono di aggiungere.
    """

    base_statement: Mapping[str, Any]
    qualification_links: tuple[EvidenceQualificationLink, ...] = ()
    linked_source_profile_ids: tuple[str, ...] = ()
    qualified_dimensions: Mapping[str, DimensionValue] = field(default_factory=dict)
    unresolved_dimensions: tuple[str, ...] = ()
    conflicts: tuple[Mapping[str, Any], ...] = ()
    qualification_status: str = UNQUALIFIED

    @property
    def statement_id(self) -> str:
        return str(self.base_statement.get("evidence_statement_id") or "")

    @property
    def hard_filterable_dimensions(self) -> tuple[str, ...]:
        """Le dimensioni con cui e' lecito escludere una evidenza.

        Oggi, sul corpus corrente, e' vuota — e non e' un difetto della vista: e'
        lo stato reale della revisione, dove nessun qualificatore ha ancora una
        seconda conferma indipendente.
        """
        return tuple(
            sorted(
                name
                for name, value in self.qualified_dimensions.items()
                if value.may_hard_filter
            )
        )

    @property
    def prototype_only_dimensions(self) -> tuple[str, ...]:
        """Mostrabili e ispezionabili, mai usabili per filtrare."""
        return tuple(
            sorted(
                name
                for name, value in self.qualified_dimensions.items()
                if not value.may_hard_filter
            )
        )

    def assert_hard_filterable(self, dimension: str) -> None:
        """Solleva se qualcuno prova a filtrare con un qualificatore prototipo.

        Esiste perche' il rifiuto sia esplicito nel punto d'uso. Un chiamante che
        legga `qualified_dimensions` e filtri senza chiedere non trova ostacoli,
        e questa e' la chiamata che glielo mette davanti.
        """
        value = self.qualified_dimensions.get(dimension)
        if value is None:
            raise PrototypeHardFilterError(
                f"{dimension} non e' qualificata su {self.statement_id}: non ci si puo' filtrare"
            )
        if not value.may_hard_filter:
            raise PrototypeHardFilterError(
                f"{dimension} su {self.statement_id} ha eligibility "
                f"{value.propagation_eligibility}: puo' essere mostrata e ispezionata, "
                "non puo' escludere evidenza. Un filtro sbagliato rimuove cio' che "
                "nessuno potra' piu' vedere"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement_id": self.statement_id,
            "base_statement": copy.deepcopy(dict(self.base_statement)),
            "qualification_links": [link.as_dict() for link in self.qualification_links],
            "linked_source_profiles": list(self.linked_source_profile_ids),
            "qualified_dimensions": {
                name: value.as_dict() for name, value in sorted(self.qualified_dimensions.items())
            },
            "unresolved_dimensions": list(self.unresolved_dimensions),
            "conflicts": [dict(c) for c in self.conflicts],
            "qualification_status": self.qualification_status,
            "hard_filterable_dimensions": list(self.hard_filterable_dimensions),
            "prototype_only_dimensions": list(self.prototype_only_dimensions),
            "provenance_by_dimension": {
                name: {
                    "value_origin": value.value_origin,
                    "source_profile_id": value.source_profile_id,
                    "source_identifier": value.source_identifier,
                    "qualification_link_id": value.qualification_link_id,
                    "review_status": value.review_status,
                }
                for name, value in sorted(self.qualified_dimensions.items())
            },
        }


def build_view(
    statement: Mapping[str, Any], links: Sequence[EvidenceQualificationLink]
) -> QualifiedEvidenceView:
    """Compone la vista per uno statement dai suoi link.

    Se due link qualificanti propongono valori diversi per la stessa dimensione, la
    dimensione **non viene applicata** e il disaccordo diventa un conflitto: scegliere
    fra due fonti revisionate e' un giudizio umano, non una regola di precedenza.
    """
    statement_id = str(statement.get("evidence_statement_id") or "")
    relevant = [link for link in links if link.statement_id == statement_id]

    proposals: dict[str, list[DimensionValue]] = {}
    conflicts: list[dict[str, Any]] = []
    for link in relevant:
        conflicts.extend(dict(c) | {"qualification_link_id": link.qualification_link_id}
                         for c in link.conflicts)
        if not link.qualifies:
            continue
        for dimension_value in link.added_dimensions:
            proposals.setdefault(dimension_value.dimension, []).append(dimension_value)

    qualified: dict[str, DimensionValue] = {}
    for dimension, values in proposals.items():
        distinct = {normalize_text(v.value) for v in values}
        if len(distinct) > 1:
            conflicts.append(
                {
                    "dimension": dimension,
                    "reason": "due profili revisionati propongono valori diversi",
                    "values": sorted(str(v.value) for v in values),
                    "resolution": "non applicata: la scelta fra fonti e' un giudizio umano",
                }
            )
            continue
        qualified[dimension] = values[0]

    unresolved = tuple(d for d in PROFILE_DIMENSIONS if d not in qualified)

    if any(link.match_status == CONFLICTING_MATCH for link in relevant) or conflicts:
        status = CONFLICTING
    elif any(link.match_status == AMBIGUOUS_MATCH for link in relevant):
        status = AMBIGUOUS
    elif not qualified:
        status = UNQUALIFIED
    elif unresolved:
        status = PARTIALLY_QUALIFIED
    else:
        status = QUALIFIED

    return QualifiedEvidenceView(
        base_statement=copy.deepcopy(dict(statement)),
        qualification_links=tuple(relevant),
        linked_source_profile_ids=tuple(sorted({link.source_profile_id for link in relevant})),
        qualified_dimensions=qualified,
        unresolved_dimensions=unresolved,
        conflicts=tuple(conflicts),
        qualification_status=status,
    )


def build_views(
    statements: Sequence[Mapping[str, Any]], links: Sequence[EvidenceQualificationLink]
) -> list[QualifiedEvidenceView]:
    by_statement: dict[str, list[EvidenceQualificationLink]] = {}
    for link in links:
        by_statement.setdefault(link.statement_id, []).append(link)
    return [
        build_view(statement, by_statement.get(
            str(statement.get("evidence_statement_id") or ""), []))
        for statement in statements
    ]
