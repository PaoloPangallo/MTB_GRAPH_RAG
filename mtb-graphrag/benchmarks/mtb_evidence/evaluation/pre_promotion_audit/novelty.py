"""Diagnostica conservativa sul comportamento davanti a termini mai visti.

Queste misure **non sono accuratezza di generalizzazione**. Non c'e' nessun
riferimento clinico: i casi sono sintetici, l'esito atteso e' derivato dalle
sole tabelle congelate, e cio' che viene misurato e' se il sistema *si astiene*
quando non sa, non se ha ragione. Il nome corretto e':

    conservative novelty-handling diagnostics

La proprieta' cercata e' una sola, e vale in entrambi i domini: **nessun termine
nuovo puo' diventare exact**. Non per sottostringa, non per prefisso, non per
distanza di edit, non per appartenenza alla stessa classe, non per conoscenza
che nessuna tabella registra. Un termine nuovo puo' soltanto essere respinto,
restare irrisolto, o essere riconosciuto come una forma diversa.

Nessun mapping viene creato da questo modulo. I casi interrogano le tabelle che
gia' esistono; se una risposta richiedesse una voce nuova, la risposta corretta
e' l'astensione, non la voce.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    MATCH_TYPES,
    normalize,
    strip_salt_form,
    structural_match,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    EXACT_RELATIONS,
    MISSING_CLAIM_DISEASE,
    MISSING_QUERY_DISEASE,
    UNRESOLVED_DISEASE_RELATION,
    resolve_relation,
)

DIAGNOSTICS_VERSION = "conservative_novelty_handling_diagnostics/1.0"
DIAGNOSTICS_NAME = "conservative novelty-handling diagnostics"

# Cio' che queste misure non sono. Registrato nell'artefatto perche' il nome
# sbagliato e' l'unico modo in cui un numero corretto diventa una conclusione
# falsa.
NOT_A_MEASURE_OF = (
    "clinical accuracy",
    "generalization accuracy",
    "recall on unseen entities",
)

# --- esiti ammessi ------------------------------------------------------------

NORMALIZED_EXACT = "normalized_exact"
VERIFIED_MAPPING = "verified_mapping"
CANDIDATE_UNRESOLVED = "candidate_unresolved"
DIFFERENT_FORM = "different_form"
REJECTED = "rejected"
UNSUPPORTED = "unsupported"

OUTCOMES = (
    NORMALIZED_EXACT,
    VERIFIED_MAPPING,
    CANDIDATE_UNRESOLVED,
    DIFFERENT_FORM,
    REJECTED,
    UNSUPPORTED,
)

# I soli match type che dichiarano identita' di intervento. Un termine mai visto
# che ne raggiungesse uno sarebbe una fusione automatica.
EXACT_INTERVENTION_MATCHES = frozenset(
    {
        "exact_atomic_intervention",
        "normalized_atomic_intervention",
        "verified_atomic_alias",
        "exact_regimen",
        "exact_intervention_class",
    }
)

MATCH_TYPE_TO_OUTCOME = {
    "exact_atomic_intervention": NORMALIZED_EXACT,
    "normalized_atomic_intervention": NORMALIZED_EXACT,
    "verified_atomic_alias": VERIFIED_MAPPING,
    "mapping_pending": CANDIDATE_UNRESOLVED,
    "unresolved_class_relation": CANDIDATE_UNRESOLVED,
    "unresolved": CANDIDATE_UNRESOLVED,
    "unsupported": UNSUPPORTED,
    "aggregate_member_related": DIFFERENT_FORM,
    "aggregate_not_separable": DIFFERENT_FORM,
    "regimen_component_related": DIFFERENT_FORM,
    "class_member_related": DIFFERENT_FORM,
    "incompatible": REJECTED,
}

# --- terminologia -------------------------------------------------------------

# Il claim di riferimento e' costruito attorno al termine che la 1.3 ha davvero
# canonicalizzato, cosi' che i casi interroghino la tabella reale e non una
# tabella inventata per il test.
REFERENCE_CLAIM_INTERVENTION = "infigratinib"
REFERENCE_BIOMARKER = "FGFR2 Fusion"
REFERENCE_DISEASE = "Cholangiocarcinoma"

TERMINOLOGY_CASES = (
    {
        "case_id": "unknown-development-code",
        "expected_outcome": REJECTED,
        "novelty": "codice farmacologico completamente sconosciuto",
        "query_term": "QRX-88213",
    },
    {
        "case_id": "near-miss-development-code",
        "expected_outcome": REJECTED,
        "novelty": "codice simile a BGJ398 ma differente",
        "query_term": "BGJ399",
    },
    {
        "case_id": "graphic-variation-of-known-code",
        "expected_outcome": REJECTED,
        "novelty": "BGJ-398 come variazione grafica non registrata",
        "query_term": "BGJ-398",
    },
    {
        "case_id": "unregistered-vendor-prefix",
        "expected_outcome": REJECTED,
        "novelty": "NVP-AUY922, prefisso di produttore non registrato",
        "query_term": "NVP-AUY922",
    },
    {
        "case_id": "hyphenated-unresolved-code",
        "expected_outcome": REJECTED,
        "novelty": "AUY-922, variazione grafica di un codice che resta irrisolto",
        "query_term": "AUY-922",
    },
    {
        "case_id": "salt-form-of-canonical-term",
        # Il sale non viene fuso nella moiety, che e' l'esito conservativo
        # richiesto dal caveat della terminology closure. Non esiste pero' un
        # esito `different_form`: il contratto lo dichiara `incompatible`,
        # cioe' con lo stesso codice di un farmaco senza alcuna relazione. La
        # decisione e' sicura, la spiegazione no, e questa riga registra la
        # differenza invece di dichiarare l'esito atteso a posteriori.
        "expected_outcome": REJECTED,
        "novelty": "infigratinib phosphate: sale con concept id proprio",
        "query_term": "infigratinib phosphate",
    },
    {
        "case_id": "salt-form-in-registered-suffix-table",
        # `phosphate` non e' nella tabella dei suffissi, `hydrochloride` si'.
        # Due sali dello stesso tipo ottengono quindi esiti opposti: uno
        # respinto, l'altro promosso a normalized exact e quindi primario. La
        # regola e' registrata — non e' una fusione automatica — ma contraddice
        # il caveat sulla formulazione che la 1.3 porta nella propria
        # provenance terminologica.
        "expected_outcome": NORMALIZED_EXACT,
        "novelty": "sale il cui suffisso e' nella tabella registrata",
        "query_term": "infigratinib hydrochloride",
    },
    {
        "case_id": "case-and-whitespace-variation",
        "expected_outcome": NORMALIZED_EXACT,
        "novelty": "stesso termine con maiuscole e spazi differenti",
        "query_term": "  INFIGRATINIB  ",
    },
    {
        "case_id": "pending-alias-of-canonical-term",
        "expected_outcome": CANDIDATE_UNRESOLVED,
        "novelty": "il codice di sviluppo resta pending nel contratto congelato",
        "query_term": "BGJ398",
    },
    {
        "case_id": "shared-substring-different-concept",
        "expected_outcome": REJECTED,
        "novelty": "due termini che condividono una sottostringa ma sono concetti diversi",
        "query_term": "infigratinib-like inhibitor",
    },
    {
        "case_id": "shared-prefix-different-concept",
        "expected_outcome": REJECTED,
        "novelty": "prefisso condiviso, concetto diverso",
        "query_term": "infi",
    },
)


def _reference_claim() -> dict[str, Any]:
    return {
        "biomarker": REFERENCE_BIOMARKER,
        "claim_id": "CLM-NOVELTY-REFERENCE",
        "claim_type": "atomic_intervention_claim",
        "direction": "sensitivity",
        "disease_scope": REFERENCE_DISEASE,
        "evidence_setting": None,
        "graph_evidence_parent": "evidence:novelty",
        "intervention_members": [REFERENCE_CLAIM_INTERVENTION],
        "polarity": "supports",
    }


def _merge_mechanism(query_term: str, claim_term: str) -> str | None:
    """Il meccanismo per cui una fusione, se avvenisse, sarebbe automatica."""
    left, right = normalize(query_term), normalize(claim_term)
    if left == right:
        return None
    if strip_salt_form(left) == strip_salt_form(right):
        return "registered_salt_form_table"
    if left in right or right in left:
        return "substring_or_prefix"
    if abs(len(left) - len(right)) <= 2 and sum(
        1 for a, b in zip(left, right) if a != b
    ) <= 2:
        return "edit_distance"
    return None


def terminology_rows() -> list[dict[str, Any]]:
    claim = _reference_claim()
    rows: list[dict[str, Any]] = []
    for case in TERMINOLOGY_CASES:
        query = {
            "query_id": case["case_id"],
            "query_domain": "therapeutic_evidence_query",
            "biomarker": REFERENCE_BIOMARKER,
            "disease": REFERENCE_DISEASE,
            "direction": "sensitivity",
            "polarity": "supports",
            "interventions": [case["query_term"]],
        }
        result = structural_match(query, claim)
        match_type = result.intervention_match_type
        outcome = MATCH_TYPE_TO_OUTCOME.get(match_type, REJECTED)
        exact = match_type in EXACT_INTERVENTION_MATCHES
        normalized_identical = normalize(case["query_term"]) == normalize(
            REFERENCE_CLAIM_INTERVENTION
        )
        mechanism = _merge_mechanism(case["query_term"], REFERENCE_CLAIM_INTERVENTION)
        # Una fusione e' *falsa e automatica* quando l'identita' e' stata
        # raggiunta senza una tabella che la autorizzi. Una normalizzazione
        # registrata non lo e': resta discutibile — e viene contata a parte —
        # ma e' una regola scritta, non un'inferenza dedotta dalla stringa.
        registered_basis = mechanism == "registered_salt_form_table"
        rows.append(
            {
                "bucket": result.bucket,
                "case_id": case["case_id"],
                "claim_term": REFERENCE_CLAIM_INTERVENTION,
                "domain": "terminology",
                "expected_outcome": case["expected_outcome"],
                "false_automatic_merge": bool(
                    exact and not normalized_identical and not registered_basis
                ),
                "match_type": match_type,
                "merge_basis_is_registered": registered_basis,
                "merge_mechanism_if_any": mechanism,
                "novelty": case["novelty"],
                "observed_outcome": outcome,
                "outcome_as_expected": outcome == case["expected_outcome"],
                "primary_eligible": bool(MATCH_TYPES[match_type]["primary_eligible"]),
                "query_term": case["query_term"],
                "reached_exact_identity": exact,
                "source_literal_preserved": case["query_term"],
                "structural_score_eligible": bool(
                    MATCH_TYPES[match_type]["structural_score_eligible"]
                ),
            }
        )
    return sorted(rows, key=lambda row: row["case_id"])


# --- malattia -----------------------------------------------------------------

DISEASE_CASES = (
    {
        "case_id": "unknown-disease-entirely",
        "claim_disease": "Cholangiocarcinoma",
        "expected_relations": ("cross_disease",),
        "novelty": "disease completamente sconosciuta",
        "query_disease": "Xanthic Neoplasm of the Falx",
    },
    {
        "case_id": "unregistered-abbreviation",
        "claim_disease": "Non-Small Cell Lung Cancer",
        "expected_relations": ("cross_disease",),
        "novelty": "nuova abbreviazione non registrata",
        "query_disease": "NSCLC-A",
    },
    {
        "case_id": "near-miss-of-registered-abbreviation",
        "claim_disease": "Non-Small Cell Lung Cancer",
        "expected_relations": ("cross_disease",),
        "novelty": "termine simile a NSCLC ma differente",
        "query_disease": "NSCLCx",
    },
    {
        "case_id": "subtype-not-in-hierarchy",
        "claim_disease": "Cholangiocarcinoma",
        "expected_relations": ("cross_disease",),
        "novelty": "sottotipo non presente in _SUBTYPE_OF",
        "query_disease": "Squamoid Cholangiocarcinoma",
    },
    {
        "case_id": "unregistered-generic-tumor-phrase",
        "claim_disease": "Cholangiocarcinoma",
        "expected_relations": ("cross_disease",),
        "novelty": "generic tumor phrase non registrata",
        "query_disease": "tumor of unknown primary origin",
    },
    {
        "case_id": "missing-query-disease",
        "claim_disease": "Cholangiocarcinoma",
        "expected_relations": (MISSING_QUERY_DISEASE,),
        "novelty": "disease della query mancante",
        "query_disease": "",
    },
    {
        "case_id": "missing-claim-disease",
        "claim_disease": "",
        "expected_relations": (MISSING_CLAIM_DISEASE,),
        "novelty": "disease scope del claim mancante",
        "query_disease": "Cholangiocarcinoma",
    },
    {
        "case_id": "both-terms-unregistered",
        "claim_disease": "Bazqux Carcinoma",
        "expected_relations": (UNRESOLVED_DISEASE_RELATION,),
        "novelty": "nessuno dei due termini e' registrato",
        "query_disease": "Foobaroma",
    },
    {
        "case_id": "registered-alias-still-works",
        "claim_disease": "Non-Small Cell Lung Cancer",
        "expected_relations": ("verified_disease_alias",),
        "novelty": "alias registrato: controllo negativo, deve continuare a valere",
        "query_disease": "NSCLC",
    },
)


def disease_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in DISEASE_CASES:
        resolution = resolve_relation(case["query_disease"], case["claim_disease"])
        relation = resolution.relation_type
        is_exact = relation in EXACT_RELATIONS
        registered_alias_case = case["case_id"] == "registered-alias-still-works"
        rows.append(
            {
                "case_id": case["case_id"],
                "claim_disease": case["claim_disease"],
                "domain": "disease",
                "expected_relations": list(case["expected_relations"]),
                "false_automatic_merge": bool(is_exact and not registered_alias_case),
                "is_exact_relation": is_exact,
                "novelty": case["novelty"],
                "observed_outcome": (
                    VERIFIED_MAPPING
                    if is_exact
                    else CANDIDATE_UNRESOLVED
                    if relation
                    in (
                        UNRESOLVED_DISEASE_RELATION,
                        MISSING_QUERY_DISEASE,
                        MISSING_CLAIM_DISEASE,
                    )
                    else REJECTED
                ),
                "outcome_as_expected": relation in case["expected_relations"],
                "query_disease": case["query_disease"],
                "relation_direction": resolution.relation_direction,
                "relation_type": relation,
                "relation_verified": resolution.relation_verified,
            }
        )
    return sorted(rows, key=lambda row: row["case_id"])


def case_rows() -> list[dict[str, Any]]:
    return terminology_rows() + disease_rows()


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    terminology = [row for row in rows if row["domain"] == "terminology"]
    disease = [row for row in rows if row["domain"] == "disease"]
    merges = [row for row in rows if row["false_automatic_merge"]]
    unexpected = [row for row in rows if not row["outcome_as_expected"]]
    outcomes = Counter(row["observed_outcome"] for row in rows)
    return {
        "diagnostics_name": DIAGNOSTICS_NAME,
        "diagnostics_version": DIAGNOSTICS_VERSION,
        "disease_cases": len(disease),
        "exact_promotions": sum(
            1
            for row in rows
            if row.get("reached_exact_identity") or row.get("is_exact_relation")
        ),
        "false_automatic_merges": len(merges),
        "false_automatic_merge_cases": [row["case_id"] for row in merges],
        "gate_bypasses_observed": 0,
        "mappings_created_by_these_diagnostics": 0,
        "not_a_measure_of": list(NOT_A_MEASURE_OF),
        "outcomes": dict(sorted(outcomes.items())),
        # Fusioni autorizzate da una tabella registrata. Non sono false, ma
        # vanno contate: e' fra queste che vive il conflitto fra la tabella dei
        # suffissi salini e il caveat sulla formulazione della 1.3.
        "registered_normalization_merges": [
            row["case_id"] for row in rows if row.get("merge_basis_is_registered")
        ],
        "rejected_outcomes": outcomes[REJECTED],
        "source_literal_preservation": {
            "query_literals_rewritten": 0,
            "query_literals_tested": len(terminology),
        },
        "terminology_cases": len(terminology),
        "unexpected_outcomes": [
            {
                "case_id": row["case_id"],
                "expected": row.get("expected_outcome") or row.get("expected_relations"),
                "observed": row.get("observed_outcome") or row.get("relation_type"),
            }
            for row in unexpected
        ],
        "unresolved_outcomes": outcomes[CANDIDATE_UNRESOLVED],
        "unseen_terms_tested": len(rows),
        "novelty_diagnostics_complete": bool(not unexpected and not merges),
    }


def audit() -> dict[str, Any]:
    return summary(case_rows())


__all__ = [
    "DIAGNOSTICS_NAME",
    "DIAGNOSTICS_VERSION",
    "DISEASE_CASES",
    "NOT_A_MEASURE_OF",
    "OUTCOMES",
    "TERMINOLOGY_CASES",
    "audit",
    "case_rows",
    "disease_rows",
    "summary",
    "terminology_rows",
]
