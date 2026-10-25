"""Contratto di retrieval e scoring per il modello dei claim tipizzati.

L'adjudication ha deciso che il parent e' un contenitore di provenienza e che le
proposizioni terapeutiche sono claim tipizzati: atomici, di regime o aggregati.
Quel modello non sopravvive al retrieval se il matching resta quello attuale, che
confronta una stringa di intervento con un insieme di stringhe della query e
tratta ogni corrispondenza come equivalente.

Il principio di questo modulo e' che il match ha **due livelli separati**:
prima l'idoneita' strutturale, poi il punteggio. Un candidato strutturalmente
incompatibile non puo' diventare compatibile con un punteggio alto. Nel sistema
attuale la stessa cosa e' espressa da penalita' numeriche — `penalty_not_separable`
vale -2 contro un `native_biomarker` da 40 — quindi non e' un vincolo ma una
preferenza. Qui diventa un gate.

Il modulo definisce e simula. Non tocca l'adapter, il corpus, il retriever
operativo, lo scoring operativo, e non assegna pesi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "claim-type-retrieval-contract/1.0"

# --- oggetti interrogabili ----------------------------------------------------

RETRIEVABLE_OBJECT_KINDS = (
    "graph_evidence_record",
    "atomic_intervention_claim",
    "aggregate_intervention_claim",
    "regimen_claim",
    "unsupported_association",
    "unresolved_association",
)

CLAIM_TYPES = (
    "atomic_intervention_claim",
    "aggregate_intervention_claim",
    "regimen_claim",
)

# Il parent non e' un claim. Puo' essere caricato per completare lineage, fonte,
# record grezzo e provenienza dell'adapter, mai per attribuire una terapia.
PARENT_KIND = "graph_evidence_record"
PARENT_ALLOWED_USES = (
    "graph_lineage",
    "source_resolution",
    "raw_record_inspection",
    "adapter_provenance",
    "audit_trail",
)
PARENT_FORBIDDEN_USES = (
    "claim_level_candidate_ranking",
    "therapy_score_assignment",
    "therapy_level_metrics",
    "primary_therapeutic_evidence_result",
)

# --- tipi di query ------------------------------------------------------------

QUERY_TYPES = (
    "no_intervention_query",
    "single_intervention_query",
    "regimen_query",
    "intervention_class_query",
    "unspecified_multi_intervention_query",
)


class ContractError(RuntimeError):
    """Il contratto e' stato usato fuori dalle sue premesse."""


def classify_query(query: Mapping[str, Any]) -> str:
    """Il tipo di query si legge dalla struttura, non dal numero di stringhe.

    Due farmaci nella query non fanno un regime: senza un indicatore strutturato
    (`intervention_combination = true`) restano due vincoli alternativi. Inferire
    la combinazione dalla cardinalita' produrrebbe exact match su regimi che
    l'utente non ha chiesto.
    """
    interventions = tuple(query.get("interventions") or ())
    if query.get("intervention_class"):
        if interventions:
            raise ContractError(
                f"{query.get('query_id')}: una query di classe non puo' portare anche interventi"
            )
        return "intervention_class_query"
    if not interventions:
        return "no_intervention_query"
    if query.get("intervention_combination"):
        if len(interventions) < 2:
            raise ContractError(
                f"{query.get('query_id')}: combinazione dichiarata con meno di due componenti"
            )
        return "regimen_query"
    if len(interventions) == 1:
        return "single_intervention_query"
    return "unspecified_multi_intervention_query"


# --- match type ---------------------------------------------------------------
# Ogni tipo porta con se' la propria idoneita'. Le regole non stanno nel
# retriever: stanno qui, dove si possono leggere tutte insieme e verificare.

MATCH_TYPES: dict[str, dict[str, Any]] = {
    "exact_atomic_intervention": {
        "definition": "La query chiede un singolo intervento e il claim atomico porta lo stesso intervento canonico.",
        "primary_eligible": True,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": True,
        "qualified_score_eligible": True,
        "reason_code": "ATOMIC_EXACT_INTERVENTION_MATCH",
        "explanation_template": "Il claim attribuisce il risultato esattamente a {claim_intervention}.",
    },
    "normalized_atomic_intervention": {
        "definition": "Stesso intervento dopo normalizzazione di forma (spazi, maiuscole, forma salina dello stesso principio attivo).",
        "primary_eligible": True,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": True,
        "qualified_score_eligible": True,
        "reason_code": "ATOMIC_NORMALIZED_INTERVENTION_MATCH",
        "explanation_template": "{query_intervention} e {claim_intervention} sono lo stesso principio attivo dopo normalizzazione.",
    },
    "verified_atomic_alias": {
        "definition": "Alias approvato localmente o identificato esplicitamente nella fonte come lo stesso intervento.",
        "primary_eligible": True,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": True,
        "qualified_score_eligible": True,
        "reason_code": "ATOMIC_VERIFIED_ALIAS_MATCH",
        "explanation_template": "{query_intervention} e' un alias verificato di {claim_intervention}.",
    },
    "exact_regimen": {
        "definition": "L'insieme dei componenti della query coincide con quello del claim dopo normalizzazione verificata. L'ordine non conta.",
        "primary_eligible": True,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": True,
        "qualified_score_eligible": True,
        "reason_code": "REGIMEN_EXACT_MATCH",
        "explanation_template": "Il claim riguarda esattamente la combinazione {claim_intervention}.",
    },
    "regimen_component_related": {
        "definition": "La query chiede un componente del regime. Il risultato appartiene alla combinazione e non al componente.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "ATOMIC_COMPONENT_NOT_REGIMEN_MATCH",
        "explanation_template": "{query_intervention} e' un componente di {claim_intervention}: il risultato e' della combinazione.",
    },
    "regimen_subset_mismatch": {
        "definition": "La combinazione chiesta e' un sottoinsieme proprio di quella del claim.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "QUERY_REGIMEN_IS_PROPER_SUBSET",
        "explanation_template": "La combinazione chiesta e' contenuta in {claim_intervention} ma non coincide.",
    },
    "regimen_superset_mismatch": {
        "definition": "La combinazione chiesta e' un sovrainsieme proprio di quella del claim.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "QUERY_REGIMEN_IS_PROPER_SUPERSET",
        "explanation_template": "La combinazione chiesta contiene {claim_intervention} ma aggiunge altri componenti.",
    },
    "exact_intervention_class": {
        "definition": "La query chiede una classe e il claim aggregato riguarda la stessa classe canonica, o un suo alias verificato.",
        "primary_eligible": True,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": True,
        "qualified_score_eligible": True,
        "reason_code": "CLASS_EXACT_MATCH",
        "explanation_template": "Il claim riguarda la classe {claim_intervention}, la stessa chiesta dalla query.",
    },
    "class_member_related": {
        "definition": "La query chiede un farmaco appartenente, per relazione verificata, alla classe del claim aggregato.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "CLASS_LEVEL_EVIDENCE_NOT_DRUG_SPECIFIC",
        "explanation_template": "Il risultato e' di classe ({claim_intervention}) e non specifico per {query_intervention}.",
    },
    "aggregate_member_related": {
        "definition": "La query chiede un farmaco nominato dentro un aggregato non separabile.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION",
        "explanation_template": "{query_intervention} compare in {claim_intervention}, ma il risultato non e' separabile per farmaco.",
    },
    "aggregate_not_separable": {
        "definition": "Il claim aggregato e' pertinente al biomarcatore ma nessun vincolo di intervento della query lo raggiunge in modo separabile.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION",
        "explanation_template": "Il risultato di {claim_intervention} non e' attribuibile a un singolo farmaco.",
    },
    "unresolved_class_relation": {
        "definition": "La relazione farmaco-classe non e' verificata localmente. Non si inferisce dalla sola stringa.",
        "primary_eligible": False,
        "warning_eligible": False,
        "audit_eligible": True,
        "structural_score_eligible": False,
        "qualified_score_eligible": False,
        "reason_code": "CLASS_RELATION_UNVERIFIED",
        "explanation_template": "Non e' verificato che {query_intervention} appartenga a {claim_intervention}.",
    },
    "mapping_pending": {
        "definition": "Il termine della query e quello del claim differiscono per un mapping terminologico non approvato.",
        "primary_eligible": False,
        "warning_eligible": False,
        "audit_eligible": True,
        "structural_score_eligible": False,
        "qualified_score_eligible": False,
        "reason_code": "INTERVENTION_MAPPING_PENDING",
        "explanation_template": "{query_intervention} e {claim_intervention} non sono verificati come lo stesso intervento.",
    },
    "unsupported": {
        "definition": "L'associazione fra intervento e record non e' sostenuta dalla fonte primaria.",
        "primary_eligible": False,
        "warning_eligible": False,
        "audit_eligible": True,
        "structural_score_eligible": False,
        "qualified_score_eligible": False,
        "reason_code": "INTERVENTION_ASSOCIATION_UNSUPPORTED_BY_SOURCE",
        "explanation_template": "La fonte non sostiene l'associazione fra {query_intervention} e questo record.",
    },
    "unresolved": {
        "definition": "Il supporto non e' determinabile: testo insufficiente, locator insufficiente, mapping pending o scope incerto.",
        "primary_eligible": False,
        "warning_eligible": True,
        "audit_eligible": True,
        "structural_score_eligible": False,
        "qualified_score_eligible": False,
        "reason_code": "DOCUMENTARY_ATTRIBUTION_UNRESOLVED",
        "explanation_template": "Il supporto documentale per {query_intervention} non e' determinabile.",
    },
    "no_intervention_constraint": {
        "definition": "La query non specifica alcuna terapia: il vincolo di intervento non si applica.",
        "primary_eligible": True,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": True,
        "reason_code": "NO_INTERVENTION_CONSTRAINT",
        "explanation_template": "La query non vincola l'intervento; il claim resta distinto per tipo.",
    },
    "incompatible": {
        "definition": "Nessuna relazione fra l'intervento della query e quello del claim.",
        "primary_eligible": False,
        "warning_eligible": False,
        "audit_eligible": False,
        "structural_score_eligible": False,
        "qualified_score_eligible": False,
        "reason_code": "NATIVE_INTERVENTION_MISMATCH",
        "explanation_template": "{query_intervention} non ha relazione con {claim_intervention}.",
    },
    "parent_not_claim": {
        "definition": "L'oggetto e' un GraphEvidenceRecord: provenienza, non proposizione terapeutica.",
        "primary_eligible": False,
        "warning_eligible": False,
        "audit_eligible": True,
        "structural_score_eligible": False,
        "qualified_score_eligible": False,
        "reason_code": "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM",
        "explanation_template": "Questo record e' un contenitore di provenienza e non porta una terapia.",
    },
}

PRIMARY_ELIGIBLE_MATCH_TYPES = frozenset(
    name for name, spec in MATCH_TYPES.items() if spec["primary_eligible"]
)
POSITIVE_SCORE_FORBIDDEN = frozenset(
    name
    for name, spec in MATCH_TYPES.items()
    if not spec["structural_score_eligible"] and not spec["qualified_score_eligible"]
)

# --- bucket -------------------------------------------------------------------

BUCKETS = (
    "primary_ranked_results",
    "retained_with_warning",
    "audit_only_results",
    "rejected_by_native_constraints",
)

WARNING_CODES = (
    "RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT",
    "CLASS_LEVEL_EVIDENCE_NOT_DRUG_SPECIFIC",
    "AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION",
    "REGIMEN_SET_DOES_NOT_COINCIDE",
    "NEGATIVE_DIRECTION_PRESERVED",
    "CONFLICTING_RESULT_PRESERVED",
    "REDUCED_SENSITIVITY_IS_NOT_RESISTANCE",
    "DIRECTION_UNKNOWN_NOT_ASSUMED_COMPATIBLE",
    "PRECLINICAL_NOT_CLINICAL_BENEFIT",
    "DOCUMENTARY_ATTRIBUTION_UNRESOLVED",
)

EXCLUSION_REASON_CODES = (
    "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM",
    "NATIVE_INTERVENTION_MISMATCH",
    "NATIVE_BIOMARKER_MISMATCH",
    "NATIVE_DISEASE_MISMATCH",
    "NATIVE_DIRECTION_MISMATCH",
    "NATIVE_POLARITY_MISMATCH",
    "ATOMIC_COMPONENT_NOT_REGIMEN_MATCH",
    "QUERY_REGIMEN_IS_PROPER_SUBSET",
    "QUERY_REGIMEN_IS_PROPER_SUPERSET",
    "CLASS_RELATION_UNVERIFIED",
    "INTERVENTION_MAPPING_PENDING",
    "INTERVENTION_ASSOCIATION_UNSUPPORTED_BY_SOURCE",
    "FULL_TEXT_REQUIRED",
    "LOCATOR_INSUFFICIENT",
    "BIOMARKER_SCOPE_UNRESOLVED",
    "DOCUMENTARY_ATTRIBUTION_UNRESOLVED",
)

# --- direzione e polarita' ----------------------------------------------------

DIRECTIONS = (
    "sensitivity",
    "resistance",
    "reduced_sensitivity",
    "unknown",
)

POLARITIES = ("supports", "does_not_support", "conflicting", "unknown")

# `reduced_sensitivity` non e' `resistance`: sono direzioni vicine e distinte, e
# collassarle trasformerebbe una risposta attenuata in una resistenza completa.
DIRECTION_MATCH = {
    ("sensitivity", "sensitivity"): "exact",
    ("resistance", "resistance"): "exact",
    ("reduced_sensitivity", "reduced_sensitivity"): "exact",
    ("resistance", "reduced_sensitivity"): "related_not_equivalent",
    ("reduced_sensitivity", "resistance"): "related_not_equivalent",
    ("sensitivity", "reduced_sensitivity"): "related_not_equivalent",
    ("reduced_sensitivity", "sensitivity"): "related_not_equivalent",
    ("sensitivity", "resistance"): "incompatible",
    ("resistance", "sensitivity"): "incompatible",
}

DIRECTION_WARNING = {
    "related_not_equivalent": "REDUCED_SENSITIVITY_IS_NOT_RESISTANCE",
    "unknown_claim_direction": "DIRECTION_UNKNOWN_NOT_ASSUMED_COMPATIBLE",
}

POLARITY_MATCH = {
    ("supports", "supports"): "exact",
    ("does_not_support", "does_not_support"): "exact",
    ("supports", "does_not_support"): "opposed",
    ("does_not_support", "supports"): "opposed",
}

POLARITY_WARNING = {
    "does_not_support": "NEGATIVE_DIRECTION_PRESERVED",
    "conflicting": "CONFLICTING_RESULT_PRESERVED",
}


def direction_match_type(query_direction: str | None, claim_direction: str) -> str:
    if not query_direction:
        return "not_constrained"
    if claim_direction == "unknown":
        return "unknown_claim_direction"
    return DIRECTION_MATCH.get((query_direction, claim_direction), "incompatible")


def polarity_match_type(query_polarity: str | None, claim_polarity: str) -> str:
    if claim_polarity == "conflicting":
        return "conflicting"
    if not query_polarity:
        return "not_constrained"
    if claim_polarity == "unknown":
        return "unknown_claim_polarity"
    return POLARITY_MATCH.get((query_polarity, claim_polarity), "opposed")


# --- disease ------------------------------------------------------------------
# La policy gerarchica non e' attiva. Le relazioni sono definite qui perche' il
# contratto resti compatibile con una futura policy ontology-aware, ma nella
# simulazione solo le prime tre valgono come hard match.

DISEASE_RELATIONS = {
    "exact": {"active": True, "primary_hard_match": True},
    "normalized_exact": {"active": True, "primary_hard_match": True},
    "verified_alias": {"active": True, "primary_hard_match": True},
    "explicit_parent": {"active": False, "primary_hard_match": False},
    "explicit_child": {"active": False, "primary_hard_match": False},
    "explicit_sibling": {"active": False, "primary_hard_match": False},
    "unresolved_disease_relation": {"active": False, "primary_hard_match": False},
}


def disease_match_type(query_disease: str | None, claim_disease: str) -> str:
    if not query_disease:
        return "not_constrained"
    if normalize(query_disease) == normalize(claim_disease):
        return "exact"
    return "unresolved_disease_relation"


# --- terminologia -------------------------------------------------------------

PENDING_ALIASES = (
    ("bgj398", "infigratinib"),
    ("auy922", "luminespib"),
    ("ch5424802", "alectinib"),
    ("17-aag", "tanespimycin"),
)

# Forme saline dello stesso principio attivo: normalizzazione, non alias.
SALT_FORM_SUFFIXES = (" hydrochloride", " hcl", " mesylate", " sulfate", " tartrate")

# Nessuna relazione farmaco-classe e' verificata localmente. Il registro esiste
# vuoto di proposito: senza una voce approvata, `erlotinib in EGFR-TKI` resta
# `unresolved_class_relation` invece di diventare una relazione dedotta dalla
# stringa.
VERIFIED_CLASS_MEMBERSHIPS: dict[str, frozenset[str]] = {}


def normalize(label: Any) -> str:
    return " ".join(str(label or "").split()).lower()


def strip_salt_form(label: str) -> str:
    normalized = normalize(label)
    for suffix in SALT_FORM_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def is_pending_pair(left: str, right: str) -> bool:
    pair = {normalize(left), normalize(right)}
    return any(pair == {code, generic} for code, generic in PENDING_ALIASES)


def class_membership_verified(drug: str, class_label: str) -> bool:
    members = VERIFIED_CLASS_MEMBERSHIPS.get(normalize(class_label), frozenset())
    return normalize(drug) in members


# --- risultato strutturale ----------------------------------------------------


@dataclass(frozen=True)
class StructuralMatchResult:
    claim_id: str
    parent_graph_evidence_id: str
    claim_type: str
    query_intervention_type: str
    query_interventions: tuple[str, ...]
    claim_interventions: tuple[str, ...]
    intervention_match_type: str
    biomarker_match_type: str
    disease_match_type: str
    direction_match_type: str
    polarity_match_type: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    bucket: str
    exclusion_reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in payload.items():
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


def intervention_match(
    query: Mapping[str, Any], claim: Mapping[str, Any], query_type: str
) -> tuple[str, tuple[str, ...]]:
    """Il tipo di match dipende dal tipo di claim, non dalla sola stringa."""
    claim_type = claim["claim_type"]
    members = tuple(normalize(item) for item in claim["intervention_members"])
    query_drugs = tuple(normalize(item) for item in (query.get("interventions") or ()))

    # Le associazioni non sono claim: il loro esito non dipende dalla query ma
    # da cio' che la fonte ha stabilito. Restano visibili in audit perche' il
    # motivo per cui non sostengono nulla e' esattamente cio' che serve sapere.
    if claim_type == "unsupported_association":
        return "unsupported", ()
    if claim_type == "unresolved_association":
        return "unresolved", ()

    if query_type == "no_intervention_query":
        return "no_intervention_constraint", ()

    if query_type == "intervention_class_query":
        wanted = normalize(query["intervention_class"])
        if claim_type == "aggregate_intervention_claim" and claim.get("aggregate_kind") == "drug_class":
            return ("exact_intervention_class", ()) if normalize(members[0]) == wanted else ("incompatible", ())
        return "incompatible", ()

    if query_type == "regimen_query":
        if claim_type != "regimen_claim":
            return "incompatible", ()
        claim_set, query_set = set(members), set(query_drugs)
        if claim_set == query_set:
            return "exact_regimen", ()
        if query_set < claim_set:
            return "regimen_subset_mismatch", tuple(sorted(claim_set - query_set))
        if claim_set < query_set:
            return "regimen_superset_mismatch", tuple(sorted(query_set - claim_set))
        return "incompatible", ()

    # query su uno o piu' interventi non dichiarati come combinazione: ogni
    # farmaco e' un vincolo alternativo, mai una combinazione implicita.
    for drug in query_drugs:
        if claim_type == "atomic_intervention_claim":
            claim_drug = members[0]
            if drug == claim_drug:
                return "exact_atomic_intervention", ()
            if strip_salt_form(drug) == strip_salt_form(claim_drug):
                return "normalized_atomic_intervention", ()
            if is_pending_pair(drug, claim_drug):
                return "mapping_pending", ()
        elif claim_type == "regimen_claim":
            if drug in members:
                return "regimen_component_related", ()
            if any(is_pending_pair(drug, member) for member in members):
                return "mapping_pending", ()
        elif claim_type == "aggregate_intervention_claim":
            if claim.get("aggregate_kind") == "drug_class":
                if class_membership_verified(drug, members[0]):
                    return "class_member_related", ()
                return "unresolved_class_relation", ()
            if drug in members:
                return "aggregate_member_related", ()
            if any(is_pending_pair(drug, member) for member in members):
                return "mapping_pending", ()
    return "incompatible", ()


def structural_match(query: Mapping[str, Any], claim: Mapping[str, Any]) -> StructuralMatchResult:
    """Idoneita' strutturale, calcolata prima e indipendentemente dal punteggio."""
    query_type = classify_query(query)
    claim_type = claim["claim_type"]
    exclusions: list[str] = []
    warnings: list[str] = []
    explanations: list[str] = []

    if claim_type == PARENT_KIND:
        return _parent_result(query, claim, query_type)

    biomarker = "exact" if normalize(query.get("biomarker")) == normalize(claim["biomarker"]) else "incompatible"
    disease = disease_match_type(query.get("disease"), claim["disease_scope"])
    direction = direction_match_type(query.get("direction"), claim["direction"])
    polarity = polarity_match_type(query.get("polarity"), claim["polarity"])
    match_type, _ = intervention_match(query, claim, query_type)

    spec = MATCH_TYPES[match_type]
    explanations.append(spec["reason_code"])

    native_ok = True
    if biomarker != "exact":
        exclusions.append("NATIVE_BIOMARKER_MISMATCH")
        native_ok = False
    if not DISEASE_RELATIONS.get(disease, {}).get("primary_hard_match") and disease != "not_constrained":
        exclusions.append("NATIVE_DISEASE_MISMATCH")
        native_ok = False
    if direction == "incompatible":
        exclusions.append("NATIVE_DIRECTION_MISMATCH")
        native_ok = False
    if polarity == "opposed":
        exclusions.append("NATIVE_POLARITY_MISMATCH")
        native_ok = False

    if direction == "related_not_equivalent":
        warnings.append(DIRECTION_WARNING["related_not_equivalent"])
    if direction == "unknown_claim_direction":
        warnings.append(DIRECTION_WARNING["unknown_claim_direction"])
    if claim["polarity"] in POLARITY_WARNING:
        warnings.append(POLARITY_WARNING[claim["polarity"]])
    if claim.get("evidence_setting") == "preclinical":
        warnings.append("PRECLINICAL_NOT_CLINICAL_BENEFIT")
    if match_type == "regimen_component_related":
        warnings.append("RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT")
    if match_type in ("regimen_subset_mismatch", "regimen_superset_mismatch"):
        warnings.append("REGIMEN_SET_DOES_NOT_COINCIDE")
    if match_type in ("class_member_related",):
        warnings.append("CLASS_LEVEL_EVIDENCE_NOT_DRUG_SPECIFIC")
    if match_type in ("aggregate_member_related", "aggregate_not_separable"):
        warnings.append("AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION")

    if match_type == "incompatible":
        exclusions.append(spec["reason_code"])
        native_ok = False
    elif match_type in ("mapping_pending", "unresolved_class_relation"):
        exclusions.append(spec["reason_code"])

    # Il gate: l'idoneita' primaria e' funzione del solo tipo strutturale e dei
    # vincoli nativi. Nessun punteggio entra in questa espressione.
    primary = bool(native_ok and spec["primary_eligible"] and direction != "related_not_equivalent")
    warning_eligible = bool(native_ok and not primary and spec["warning_eligible"])
    audit_only = bool(spec["audit_eligible"] and not primary and not warning_eligible)

    if native_ok and direction == "related_not_equivalent" and spec["primary_eligible"]:
        warning_eligible = True

    # Il vincolo nativo viene prima della classificazione per tipo. Un'associazione
    # non sostenuta su un biomarcatore che la query non chiede non e' materiale di
    # audit per quella query: e' semplicemente fuori perimetro. Tenerla in audit
    # riempirebbe il bucket di oggetti irrilevanti e renderebbe illeggibile cio'
    # che invece va guardato.
    if not native_ok:
        audit_only = False
        warning_eligible = False
        bucket = "rejected_by_native_constraints"
    elif primary:
        bucket = "primary_ranked_results"
    elif warning_eligible:
        bucket = "retained_with_warning"
    else:
        bucket = "audit_only_results"

    return StructuralMatchResult(
        claim_id=claim["claim_id"],
        parent_graph_evidence_id=claim["graph_evidence_parent"],
        claim_type=claim_type,
        query_intervention_type=query_type,
        query_interventions=tuple(query.get("interventions") or ()) or (
            (query.get("intervention_class"),) if query.get("intervention_class") else ()
        ),
        claim_interventions=tuple(claim["intervention_members"]),
        intervention_match_type=match_type,
        biomarker_match_type=biomarker,
        disease_match_type=disease,
        direction_match_type=direction,
        polarity_match_type=polarity,
        primary_candidate_eligible=primary,
        warning_eligible=warning_eligible,
        audit_only=audit_only,
        bucket=bucket,
        exclusion_reason_codes=tuple(dict.fromkeys(exclusions)),
        warning_codes=tuple(dict.fromkeys(warnings)),
        explanation_codes=tuple(dict.fromkeys(explanations)),
    )


def _parent_result(
    query: Mapping[str, Any], claim: Mapping[str, Any], query_type: str
) -> StructuralMatchResult:
    spec = MATCH_TYPES["parent_not_claim"]
    return StructuralMatchResult(
        claim_id=claim["claim_id"],
        parent_graph_evidence_id=claim["graph_evidence_parent"],
        claim_type=PARENT_KIND,
        query_intervention_type=query_type,
        query_interventions=tuple(query.get("interventions") or ()),
        claim_interventions=(),
        intervention_match_type="parent_not_claim",
        biomarker_match_type="not_applicable",
        disease_match_type="not_applicable",
        direction_match_type="not_applicable",
        polarity_match_type="not_applicable",
        primary_candidate_eligible=False,
        warning_eligible=False,
        audit_only=True,
        bucket="audit_only_results",
        exclusion_reason_codes=(spec["reason_code"],),
        warning_codes=(),
        explanation_codes=(spec["reason_code"],),
    )


# --- idoneita' allo scoring ---------------------------------------------------


def score_eligibility(match: StructuralMatchResult) -> dict[str, Any]:
    """Tre livelli distinti: strutturale, qualificato, ranking finale."""
    spec = MATCH_TYPES[match.intervention_match_type]
    positive_forbidden = match.intervention_match_type in POSITIVE_SCORE_FORBIDDEN
    return {
        "claim_id": match.claim_id,
        "intervention_match_type": match.intervention_match_type,
        "structural_score_eligible": bool(spec["structural_score_eligible"] and match.bucket != "rejected_by_native_constraints"),
        "qualified_score_eligible": bool(spec["qualified_score_eligible"] and match.bucket != "rejected_by_native_constraints"),
        "final_ranking_eligible": match.primary_candidate_eligible,
        "positive_score_forbidden": positive_forbidden,
        "ranks_within_bucket_only": match.bucket == "retained_with_warning",
        "bucket": match.bucket,
    }


def check_no_numerical_compensation(
    match: StructuralMatchResult, hypothetical_score: float
) -> None:
    """Il tipo strutturale ha precedenza sui pesi, e questo lo rende verificabile.

    La funzione ricalcola l'idoneita' ignorando il punteggio: se un punteggio
    alto potesse cambiarla, questo controllo fallirebbe. Serve a rendere
    l'invariante un test e non una promessa nella documentazione.
    """
    spec = MATCH_TYPES[match.intervention_match_type]
    if match.primary_candidate_eligible and not spec["primary_eligible"]:
        raise ContractError(
            f"{match.claim_id}: idoneita' primaria concessa a un match {match.intervention_match_type}"
            f" (punteggio ipotetico {hypothetical_score})"
        )
    if match.intervention_match_type in POSITIVE_SCORE_FORBIDDEN and hypothetical_score > 0:
        raise ContractError(
            f"{match.claim_id}: punteggio positivo su un match {match.intervention_match_type}"
        )
