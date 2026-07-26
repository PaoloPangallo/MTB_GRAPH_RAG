"""Gate strutturale consapevole del dominio.

Estende il gate 1.0 con una decisione che viene prima di tutte le altre: il
dominio del claim e quello della query devono corrispondere. Non e' un filtro
piu' fine dello stesso genere di quelli che c'erano — e' un filtro di genere
diverso. Il gate 1.0 decide se un claim terapeutico *risponde bene* a una query
terapeutica; questo decide se le due cose parlano della stessa domanda.

Una query diagnostica che restituisse un claim terapeutico non commetterebbe un
errore di ranking ma un errore di categoria, e gli errori di categoria non si
vedono guardando i punteggi: il risultato sembra ragionevole, e' solo la risposta
a un'altra domanda.

Per questo il confronto numerico fra domini non e' sconsigliato ma impossibile:
`rank_within_domain` ordina dentro un dominio e non esiste una funzione che
ordini fra domini.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from backend.pipeline.evidence.shadow import structural_gates as GATE_V10
from backend.pipeline.evidence.shadow.domain import (
    ALL_CLAIM_TYPES,
    CLAIM_DOMAINS,
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
    DomainError,
    domain_for_claim_type,
    domain_of,
)
from backend.pipeline.evidence.shadow.schema import STRUCTURAL_GATE_VERSION_V11
from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import normalize

GATE_VERSION = STRUCTURAL_GATE_VERSION_V11

PRIMARY_BUCKET = GATE_V10.PRIMARY_BUCKET
WARNING_BUCKET = GATE_V10.WARNING_BUCKET
AUDIT_BUCKET = GATE_V10.AUDIT_BUCKET
REJECTED_BUCKET = GATE_V10.REJECTED_BUCKET

QUERY_DOMAINS = (
    "therapeutic_evidence_query",
    "diagnostic_evidence_query",
    "prognostic_evidence_query",
    "untyped_evidence_query",
)

UNTYPED_QUERY = "untyped_evidence_query"

QUERY_DOMAIN_TO_CLAIM_DOMAIN = {
    "therapeutic_evidence_query": DOMAIN_THERAPEUTIC,
    "diagnostic_evidence_query": DOMAIN_DIAGNOSTIC,
    "prognostic_evidence_query": DOMAIN_PROGNOSTIC,
}

SECTION_FOR_DOMAIN = {
    DOMAIN_THERAPEUTIC: "therapeutic_results",
    DOMAIN_DIAGNOSTIC: "diagnostic_results",
    DOMAIN_PROGNOSTIC: "prognostic_results",
}

REASON_CODES = (
    "CLAIM_DOMAIN_QUERY_DOMAIN_MISMATCH",
    "UNTYPED_QUERY_REQUIRES_SECTIONED_RESULTS",
    "DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC",
    "PROGNOSTIC_CLAIM_NOT_PREDICTIVE",
    "THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC",
)

# Il codice specifico da emettere per ogni disallineamento, quando ne esiste uno
# che dice qualcosa in piu' del generico.
SPECIFIC_MISMATCH = {
    ("therapeutic_evidence_query", DOMAIN_DIAGNOSTIC): "DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC",
    ("therapeutic_evidence_query", DOMAIN_PROGNOSTIC): "PROGNOSTIC_CLAIM_NOT_PREDICTIVE",
    ("diagnostic_evidence_query", DOMAIN_THERAPEUTIC): "THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC",
    ("prognostic_evidence_query", DOMAIN_THERAPEUTIC): "THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC",
    ("prognostic_evidence_query", DOMAIN_DIAGNOSTIC): "CLAIM_DOMAIN_QUERY_DOMAIN_MISMATCH",
    ("diagnostic_evidence_query", DOMAIN_PROGNOSTIC): "CLAIM_DOMAIN_QUERY_DOMAIN_MISMATCH",
}


class DomainGateError(RuntimeError):
    """Il gate di dominio e' stato aggirato o interrogato fuori ordine."""


def query_domain(query: Mapping[str, Any]) -> str:
    """Dominio dichiarato dalla query. Assente significa senza tipo, non terapeutico."""
    declared = query.get("query_domain") or query.get("domain")
    if declared is None:
        return UNTYPED_QUERY
    if declared in QUERY_DOMAINS:
        return declared
    # Forma abbreviata: `domain: therapeutic`.
    for name, claim_domain in QUERY_DOMAIN_TO_CLAIM_DOMAIN.items():
        if declared == claim_domain:
            return name
    raise DomainGateError(f"dominio di query sconosciuto: {declared!r}")


@dataclass(frozen=True)
class DomainMatchResult:
    """Esito del gate 1.1: dominio, poi struttura, poi — mai qui — punteggio."""

    claim_id: str
    parent_graph_evidence_id: str
    claim_domain: str
    claim_type: str
    query_domain: str
    domain_match: bool
    section: str | None
    bucket: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    structural_match: dict[str, Any] = field(default_factory=dict)
    score_eligibility: dict[str, Any] = field(default_factory=dict)
    therapy_score_allowed: bool = False
    cross_domain_ranking_allowed: bool = False
    exclusion_reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    gate_version: str = GATE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "parent_graph_evidence_id": self.parent_graph_evidence_id,
            "claim_domain": self.claim_domain,
            "claim_type": self.claim_type,
            "query_domain": self.query_domain,
            "domain_match": self.domain_match,
            "section": self.section,
            "bucket": self.bucket,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "warning_eligible": self.warning_eligible,
            "audit_only": self.audit_only,
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "structural_match": dict(self.structural_match),
            "score_eligibility": dict(self.score_eligibility),
            "therapy_score_allowed": self.therapy_score_allowed,
            "cross_domain_ranking_allowed": False,
            "exclusion_reason_codes": list(self.exclusion_reason_codes),
            "warning_codes": list(self.warning_codes),
            "explanation_codes": list(self.explanation_codes),
            "gate_version": self.gate_version,
        }


def _non_therapeutic_structural_match(
    query: Mapping[str, Any], claim: Any
) -> tuple[bool, tuple[str, ...], dict[str, Any]]:
    """Compatibilita' nativa di un claim non terapeutico. Nessun intervento entra.

    I vincoli sono quelli che hanno senso per il dominio: biomarcatore e disease.
    Il vincolo di intervento non viene applicato ne' rilassato — semplicemente
    non esiste per questi claim, e una query che ne porti uno non li raggiunge.
    """
    exclusions: list[str] = []
    wanted_biomarker = normalize(query.get("biomarker"))
    claim_biomarker = normalize(claim.biomarker)
    biomarker_match = "exact" if wanted_biomarker == claim_biomarker else "incompatible"
    if wanted_biomarker and biomarker_match != "exact":
        exclusions.append("NATIVE_BIOMARKER_MISMATCH")

    wanted_disease = normalize(query.get("disease"))
    claim_disease = normalize(claim.disease_scope)
    if not wanted_disease:
        disease_match = "not_constrained"
    elif wanted_disease == claim_disease:
        disease_match = "exact"
    else:
        disease_match = "unresolved_disease_relation"
        exclusions.append("NATIVE_DISEASE_MISMATCH")

    # Una query che chiede un intervento non parla di questi claim.
    if query.get("interventions") or query.get("intervention_class"):
        exclusions.append("NON_THERAPEUTIC_CLAIM_HAS_NO_INTERVENTION_TO_MATCH")

    native_ok = not exclusions
    detail = {
        "biomarker_match_type": biomarker_match,
        "disease_match_type": disease_match,
        "intervention_match_type": "not_applicable",
        "polarity_match_type": "exact"
        if not query.get("polarity") or query.get("polarity") == claim.polarity
        else "opposed",
        "direction_match_type": "not_applicable",
    }
    if detail["polarity_match_type"] == "opposed":
        exclusions.append("NATIVE_POLARITY_MISMATCH")
        native_ok = False
    return native_ok, tuple(dict.fromkeys(exclusions)), detail


def evaluate(query: Mapping[str, Any], obj: Any) -> DomainMatchResult:
    """Applica il gate di dominio e poi quello strutturale. Nessun punteggio."""
    qdomain = query_domain(query)
    claim_type = getattr(obj, "claim_type", None)
    kind = getattr(obj, "kind", None)

    # Parent e associazioni non hanno dominio: restano gestiti dal gate 1.0, che
    # li manda in audit. Non appartengono a nessuna sezione.
    if claim_type is None or kind in (
        "graph_evidence_record",
        "unsupported_association",
        "unresolved_association",
    ):
        base = GATE_V10.evaluate(query, obj)
        return DomainMatchResult(
            claim_id=base.claim_id,
            parent_graph_evidence_id=base.parent_graph_evidence_id,
            claim_domain="not_applicable",
            claim_type=base.claim_type,
            query_domain=qdomain,
            domain_match=False,
            section=None,
            bucket=base.bucket,
            primary_candidate_eligible=False,
            warning_eligible=base.warning_eligible,
            audit_only=base.audit_only,
            rejected_by_native_constraints=base.rejected_by_native_constraints,
            structural_match=base.to_dict(),
            score_eligibility=dict(base.score_eligibility),
            therapy_score_allowed=False,
            exclusion_reason_codes=base.exclusion_reason_codes,
            warning_codes=base.warning_codes,
            explanation_codes=base.explanation_codes,
        )

    cdomain = domain_of(obj)
    section = SECTION_FOR_DOMAIN[cdomain]
    domain_match = qdomain == UNTYPED_QUERY or QUERY_DOMAIN_TO_CLAIM_DOMAIN[qdomain] == cdomain

    # --- disallineamento di dominio: si ferma qui ----------------------------
    if not domain_match:
        code = SPECIFIC_MISMATCH.get(
            (qdomain, cdomain), "CLAIM_DOMAIN_QUERY_DOMAIN_MISMATCH"
        )
        return DomainMatchResult(
            claim_id=obj.claim_id,
            parent_graph_evidence_id=obj.graph_evidence_id,
            claim_domain=cdomain,
            claim_type=claim_type,
            query_domain=qdomain,
            domain_match=False,
            section=section,
            bucket=AUDIT_BUCKET,
            primary_candidate_eligible=False,
            warning_eligible=False,
            audit_only=True,
            rejected_by_native_constraints=False,
            structural_match={"intervention_match_type": "not_evaluated_domain_mismatch"},
            score_eligibility={
                "structural_score_eligible": False,
                "qualified_score_eligible": False,
                "final_ranking_eligible": False,
                "positive_score_forbidden": True,
                "ranks_within_bucket_only": False,
                "bucket": AUDIT_BUCKET,
            },
            therapy_score_allowed=False,
            exclusion_reason_codes=(code,),
            explanation_codes=(code,),
        )

    # --- dominio terapeutico: delega al gate 1.0, invariato ------------------
    if cdomain == DOMAIN_THERAPEUTIC:
        base = GATE_V10.evaluate(query, obj)
        return DomainMatchResult(
            claim_id=base.claim_id,
            parent_graph_evidence_id=base.parent_graph_evidence_id,
            claim_domain=cdomain,
            claim_type=claim_type,
            query_domain=qdomain,
            domain_match=True,
            section=section,
            bucket=base.bucket,
            primary_candidate_eligible=base.primary_candidate_eligible,
            warning_eligible=base.warning_eligible,
            audit_only=base.audit_only,
            rejected_by_native_constraints=base.rejected_by_native_constraints,
            structural_match=base.to_dict(),
            score_eligibility=dict(base.score_eligibility),
            therapy_score_allowed=True,
            exclusion_reason_codes=base.exclusion_reason_codes,
            warning_codes=base.warning_codes,
            explanation_codes=base.explanation_codes,
        )

    # --- dominio non terapeutico --------------------------------------------
    native_ok, exclusions, detail = _non_therapeutic_structural_match(query, obj)
    deprecated = bool(getattr(obj, "deprecated", False))
    if deprecated:
        exclusions = exclusions + ("CLAIM_DEPRECATED",)

    if not native_ok:
        bucket = REJECTED_BUCKET
        primary = warning = audit = False
    elif deprecated:
        bucket, primary, warning, audit = AUDIT_BUCKET, False, False, True
    else:
        bucket, primary, warning, audit = PRIMARY_BUCKET, True, False, False

    return DomainMatchResult(
        claim_id=obj.claim_id,
        parent_graph_evidence_id=obj.graph_evidence_id,
        claim_domain=cdomain,
        claim_type=claim_type,
        query_domain=qdomain,
        domain_match=True,
        section=section,
        bucket=bucket,
        primary_candidate_eligible=primary,
        warning_eligible=warning,
        audit_only=audit,
        rejected_by_native_constraints=not native_ok,
        structural_match=detail,
        score_eligibility={
            "structural_score_eligible": bool(primary),
            "qualified_score_eligible": bool(primary),
            "final_ranking_eligible": bool(primary),
            # Il punteggio terapeutico e' vietato, non assente per caso.
            "therapy_score_forbidden": True,
            "positive_score_forbidden": not primary,
            "ranks_within_bucket_only": False,
            "bucket": bucket,
        },
        therapy_score_allowed=False,
        exclusion_reason_codes=exclusions,
        explanation_codes=(f"{cdomain.upper()}_CLAIM_DOMAIN_MATCH",) if primary else (),
    )


# --- ordinamento --------------------------------------------------------------


def rank_within_domain(results: Sequence[DomainMatchResult]) -> list[DomainMatchResult]:
    """Ordinamento deterministico non clinico, dentro un solo dominio.

    Non esiste una funzione che ordini fra domini: e' il modo in cui il divieto
    di ranking cross-domain e' reso impossibile invece che sconsigliato. Chiamare
    questa funzione su risultati di domini diversi solleva.
    """
    domains = {r.claim_domain for r in results if r.claim_domain != "not_applicable"}
    if len(domains) > 1:
        raise DomainGateError(
            f"ordinamento cross-domain richiesto su {sorted(domains)}: i domini non "
            "sono confrontabili numericamente"
        )
    return sorted(results, key=lambda r: (r.claim_type, r.parent_graph_evidence_id, r.claim_id))


def section_results(
    results: Sequence[DomainMatchResult],
) -> dict[str, list[DomainMatchResult]]:
    """Risultati divisi per sezione, ognuna ordinata dentro il proprio dominio."""
    sections: dict[str, list[DomainMatchResult]] = {
        name: [] for name in SECTION_FOR_DOMAIN.values()
    }
    for result in results:
        if result.section in sections:
            sections[result.section].append(result)
    return {name: rank_within_domain(items) for name, items in sections.items()}
