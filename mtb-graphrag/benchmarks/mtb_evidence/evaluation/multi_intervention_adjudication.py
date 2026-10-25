"""Adjudication dei gruppi multi-intervento e contratto di schema parent/claim.

Il confronto fra prima revisione e replica ha lasciato una domanda strutturale
aperta: il parent e' una proposizione terapeutica o un contenitore di
provenienza? Finche' non e' decisa, il numero di claim non e' determinabile
dalle fonti. Questo modulo porta il vocabolario della fase che la decide e che
adjudica i 12 gruppi rimasti.

L'adjudication non e' indipendente se la esegue l'autore: `ADJUDICATOR_LABELS`
lo dichiara e i test lo verificano. Il tetto di cio' che la fase puo' produrre
resta `prototype_only`: nessuna decisione diventa gold clinico, nessuno statement
operativo viene rigenerato, l'adapter non viene toccato. Cio' che viene prodotto
e' una **specifica** di migrazione, non una migrazione.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping, Sequence

ADJUDICATION_VERSION = "multi-intervention-adjudication/1.0"

# Eseguita dall'autore, sugli stessi artefatti che ha prodotto. Non e' una
# revisione esterna e non viene dichiarata tale.
ADJUDICATOR_LABELS = {
    "adjudicator_role": "author_adjudicator",
    "adjudication_independence": "non_independent",
    "adjudication_status": "completed",
    "propagation_policy": "prototype_only",
    "hard_filterable": False,
    "final_clinical_gold": False,
    "gold_used_for_decisions": False,
}


class AdjudicationError(RuntimeError):
    """Una decisione non e' sostenuta dalle sue premesse."""


class ScopeMismatch(AdjudicationError):
    """Il perimetro adjudicato non coincide con quello dichiarato."""


class ProhibitedInference(AdjudicationError):
    """La decisione trasformerebbe la fonte in qualcosa che non dice."""


# --- semantica del parent -----------------------------------------------------

PARENT_SEMANTICS_OPTIONS = (
    "parent_is_therapeutic_claim",
    "parent_is_provenance_container",
    "mixed_parent_semantics",
)

PARENT_SEMANTICS_DECISION = "parent_is_provenance_container"

# Cio' che il parent conserva e cio' che smette di fare. La seconda lista e' la
# parte operativa: senza di essa il parent resterebbe un claim di fatto.
PARENT_RETAINS = (
    "graph_evidence_id",
    "original_v2_record",
    "source_identity",
    "provenance",
    "raw_fields",
    "adapter_lineage",
    "non_materialized_associations",
    "review_state",
)

PARENT_NO_LONGER = (
    "counted_as_therapy_claim",
    "classified_as_autonomous_therapeutic_support",
    "returned_as_primary_claim",
    "evaluated_in_claim_level_metrics",
    "used_as_automatic_substitute_for_the_first_child",
)

# --- tipi di claim ------------------------------------------------------------

CLAIM_TYPES = (
    "atomic_intervention_claim",
    "aggregate_intervention_claim",
    "regimen_claim",
)

ASSOCIATION_OUTCOMES = (
    "atomic_intervention_claim",
    "aggregate_intervention_claim_member",
    "regimen_claim_component",
    "unsupported_association",
    "unresolved_association",
)

MATERIALIZED_OUTCOMES = frozenset(
    {
        "atomic_intervention_claim",
        "aggregate_intervention_claim_member",
        "regimen_claim_component",
    }
)

GROUP_ADJUDICATIONS = (
    "atomic_children_approved",
    "aggregate_claim_approved",
    "regimen_claim_approved",
    "mixed_claim_structure_approved",
    "unsupported_associations_rejected",
    "unresolved_deferred",
    "terminology_review_required",
    "source_review_required",
)

ADDITIONAL_REVIEWS = ("terminology_review", "source_review", "none")

REASON_CODES = (
    "PARENT_INTERVENTION_NOT_PRESENT_IN_SOURCE",
    "CLASS_LEVEL_RESULT_ONLY",
    "SPECIFIC_DRUG_ATTRIBUTION_UNSUPPORTED",
    "AGGREGATE_CLAIM_SUPPORTED",
    "BIOMARKER_SCOPE_MISMATCH",
    "RESULT_ONLY_FOR_UNCOMMON_MUTATIONS",
    "CLAIM_BIOMARKER_NOT_SUPPORTED",
    "CLAIM_SCOPE_REQUIRES_NARROWING",
    "SEPARATE_ARM_RESULT_SUPPORTED",
    "REGIMEN_RESULT_NOT_PROPAGATED_TO_COMPONENTS",
    "PRIOR_LINE_NOT_A_CLAIM",
    "COMPARATOR_ROLE_PREVAILS",
    "PENDING_ALIAS_BLOCKS_MATERIALIZATION",
    "RESULT_NOT_LOCALIZABLE_IN_ACCESSIBLE_TEXT",
    "PARENT_CONTAINER_REQUIRES_EXPLICIT_CHILD",
    "DUPLICATE_UNIT_MERGED_INTO_SINGLE_CLAIM",
)

# --- mapping pending ----------------------------------------------------------
# Restano non verificati. Il codice di sviluppo non puo' essere canonicalizzato
# insieme al nome generico, ne' comparire in un claim approvato al suo posto.
PENDING_ALIASES = (
    ("BGJ398", "infigratinib"),
    ("AUY922", "luminespib"),
    ("CH5424802", "alectinib"),
    ("17-AAG", "tanespimycin"),
)

TERMINOLOGY_ACTIONS = (
    "defer",
    "terminology_review_required",
    "source_sufficient_to_verify",
    "do_not_materialize",
)


def pending_generic_names() -> frozenset[str]:
    return frozenset(generic.lower() for _, generic in PENDING_ALIASES)


def pending_codes() -> frozenset[str]:
    return frozenset(code.lower() for code, _ in PENDING_ALIASES)


# --- identita' dei claim ------------------------------------------------------

# I nomi dei campi sono quelli del record di claim. `graph_evidence_parent`
# porta il graph evidence ID: un solo nome per un solo valore, altrimenti il
# record e la formula divergono e l'ID dipende da quale dei due si legge.
CLAIM_ID_FIELDS = (
    "graph_evidence_parent",
    "claim_type",
    "canonical_intervention_or_regimen",
    "biomarker",
    "direction",
    "polarity",
    "source_unit_id",
)

CLAIM_ID_FORMULA = (
    "sha256(graph_evidence_id + claim_type + canonical_intervention_or_regimen"
    " + biomarker + direction + polarity + source_unit_id)"
)

CLAIM_ID_PREFIX = "CLM-"
CLAIM_ID_DIGEST_CHARS = 20


def canonical_regimen(components: Sequence[str]) -> str:
    """I componenti sono ordinati, cosi' l'ID non dipende da come sono scritti.

    L'ordinamento e' l'unica normalizzazione applicata: i termini restano quelli
    della fonte. Un codice di sviluppo non viene sostituito dal nome generico
    nemmeno qui, altrimenti l'ID renderebbe stabile un'equivalenza non
    verificata.
    """
    cleaned = [" ".join(str(item).split()).lower() for item in components]
    if len(set(cleaned)) != len(cleaned):
        raise AdjudicationError(f"componenti duplicati nel regime: {components}")
    return " + ".join(sorted(cleaned))


def canonical_intervention(label: str) -> str:
    return " ".join(str(label).split()).lower()


def claim_identity_payload(claim: Mapping[str, Any]) -> str:
    return "|".join(str(claim[field]) for field in CLAIM_ID_FIELDS)


def claim_id(claim: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(claim_identity_payload(claim).encode("utf-8")).hexdigest()
    return f"{CLAIM_ID_PREFIX}{digest[:CLAIM_ID_DIGEST_CHARS]}"


def full_claim_digest(claim: Mapping[str, Any]) -> str:
    return hashlib.sha256(claim_identity_payload(claim).encode("utf-8")).hexdigest()


def check_claim_ids(claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Gli ID devono essere stabili, indipendenti dall'ordine e non collidere."""
    identities = [claim_identity_payload(claim) for claim in claims]
    ids = [claim_id(claim) for claim in claims]
    collisions = sorted(
        {
            value
            for value in ids
            if ids.count(value) > 1
        }
    )
    distinct_identities = len(set(identities))
    if collisions:
        raise AdjudicationError(f"collisione di claim_id: {collisions}")
    if distinct_identities != len(claims):
        raise AdjudicationError("due claim condividono la stessa identita' semantica")
    reversed_ids = [claim_id(claim) for claim in reversed(claims)]
    return {
        "claim_count": len(claims),
        "distinct_identities": distinct_identities,
        "distinct_ids": len(set(ids)),
        "collision_count": len(collisions),
        "order_independent": sorted(ids) == sorted(reversed_ids),
        "stable_on_recomputation": ids == [claim_id(claim) for claim in claims],
        "digest_characters": CLAIM_ID_DIGEST_CHARS,
        "formula": CLAIM_ID_FORMULA,
    }


# --- regole di materializzazione ---------------------------------------------

REQUIRED_CLAIM_FIELDS = (
    "graph_evidence_parent",
    "source_id",
    "source_unit_id",
    "locator",
    "locator_sufficient",
    "biomarker",
    "disease_scope",
    "canonical_intervention_or_regimen",
    "direction",
    "polarity",
    "result_attributable_to_intervention",
    "aggregate_to_specific_used",
    "pending_alias_used_as_equivalence",
)


def check_claim_is_materializable(claim: Mapping[str, Any]) -> None:
    """Un claim esiste solo se ogni premessa e' presente e nessun divieto e' violato."""
    missing = [field for field in REQUIRED_CLAIM_FIELDS if field not in claim]
    if missing:
        raise ScopeMismatch(f"claim incompleto {claim.get('claim_id')}: {missing}")
    if claim["claim_type"] not in CLAIM_TYPES:
        raise ScopeMismatch(f"tipo di claim sconosciuto: {claim['claim_type']}")

    name = claim.get("claim_id") or claim["graph_evidence_parent"]
    for field in (
        "graph_evidence_parent",
        "source_id",
        "source_unit_id",
        "biomarker",
        "direction",
        "polarity",
        "canonical_intervention_or_regimen",
    ):
        if not str(claim[field] or "").strip():
            raise ScopeMismatch(f"{name}: campo obbligatorio vuoto: {field}")

    # Il disease scope puo' essere `unknown`, ma esplicito: l'assenza del campo
    # e' diversa dall'affermazione che lo scope non e' noto.
    if not str(claim["disease_scope"] or "").strip():
        raise ScopeMismatch(f"{name}: disease_scope deve essere esplicito, anche se unknown")

    if not claim["locator_sufficient"]:
        raise ProhibitedInference(f"{name}: claim approvato senza locator sufficiente")
    if not claim["result_attributable_to_intervention"]:
        raise ProhibitedInference(f"{name}: risultato non attribuibile all'intervento")
    if claim["aggregate_to_specific_used"]:
        raise ProhibitedInference(f"{name}: aggregate_to_specific")
    if claim["pending_alias_used_as_equivalence"]:
        raise ProhibitedInference(f"{name}: mapping pending usato come equivalenza")

    if claim["claim_type"] == "regimen_claim":
        components = claim.get("regimen_components") or []
        if len(components) < 2:
            raise ScopeMismatch(f"{name}: un regime richiede almeno due componenti")
        if claim["canonical_intervention_or_regimen"] != canonical_regimen(components):
            raise ScopeMismatch(f"{name}: regime non canonicalizzato")
    elif claim.get("regimen_components"):
        raise ScopeMismatch(f"{name}: componenti di regime su un claim non-regime")

    if claim["claim_type"] == "aggregate_intervention_claim":
        if not claim.get("aggregate_members"):
            raise ScopeMismatch(f"{name}: claim aggregato senza membri dichiarati")
        if claim.get("permits_member_specific_claims"):
            raise ProhibitedInference(
                f"{name}: un claim aggregato non autorizza claim per singolo membro"
            )

    check_no_pending_alias_promoted(claim)


def check_no_pending_alias_promoted(claim: Mapping[str, Any]) -> None:
    """Un nome generico pending non puo' comparire in un claim approvato.

    Vale in particolare per il caso in cui la fonte usa il solo codice di
    sviluppo: sostituirlo col nome generico dentro un claim renderebbe stabile
    un'equivalenza che nessuno ha verificato.
    """
    canonical = str(claim["canonical_intervention_or_regimen"]).lower()
    literals = {str(item).lower() for item in (claim.get("source_literal_terms") or [])}
    for code, generic in PENDING_ALIASES:
        if generic.lower() in canonical and code.lower() in literals:
            raise ProhibitedInference(
                f"{claim.get('claim_id')}: {code} promosso a {generic} in un claim approvato"
            )
        if generic.lower() in canonical and code.lower() in canonical:
            raise ProhibitedInference(
                f"{claim.get('claim_id')}: {code} e {generic} canonicalizzati insieme"
            )


def check_group_adjudication(decision: str, associations: Sequence[Mapping[str, Any]]) -> None:
    """La decisione di gruppo deve riflettere i tipi di claim effettivamente approvati."""
    if decision not in GROUP_ADJUDICATIONS:
        raise ScopeMismatch(f"decisione di gruppo sconosciuta: {decision}")
    if not associations:
        raise ScopeMismatch(f"decisione senza associazioni: {decision}")

    group = associations[0]["graph_evidence_id"]
    outcomes = {row["association_outcome"] for row in associations}
    unknown = outcomes - set(ASSOCIATION_OUTCOMES)
    if unknown:
        raise ScopeMismatch(f"{group}: esiti sconosciuti {sorted(unknown)}")

    approved_types = set()
    if "atomic_intervention_claim" in outcomes:
        approved_types.add("atomic")
    if "aggregate_intervention_claim_member" in outcomes:
        approved_types.add("aggregate")
    if "regimen_claim_component" in outcomes:
        approved_types.add("regimen")

    if decision == "atomic_children_approved" and approved_types != {"atomic"}:
        raise ScopeMismatch(f"{group}: atomic_children_approved con tipi {sorted(approved_types)}")
    if decision == "regimen_claim_approved" and approved_types != {"regimen"}:
        raise ScopeMismatch(f"{group}: regimen_claim_approved con tipi {sorted(approved_types)}")
    if decision == "mixed_claim_structure_approved" and len(approved_types) < 2:
        raise ScopeMismatch(
            f"{group}: mixed_claim_structure_approved richiede piu' di un tipo di claim"
        )
    if decision in ("unsupported_associations_rejected", "unresolved_deferred") and approved_types:
        raise ScopeMismatch(f"{group}: {decision} non puo' approvare claim")
    if decision == "unsupported_associations_rejected" and outcomes != {"unsupported_association"}:
        raise ScopeMismatch(f"{group}: tutte le associazioni devono essere unsupported")


def check_no_regimen_split(
    claims: Sequence[Mapping[str, Any]], associations: Sequence[Mapping[str, Any]]
) -> None:
    """Un claim atomico non puo' nascere dal risultato di un regime.

    Un intervento puo' avere sia un ruolo di componente sia un claim atomico —
    accade quando la fonte gli attribuisce un esito in un'unita' diversa dal
    regime — ma allora le due cose devono poggiare su `source_unit_id` distinti.
    """
    regimen_units = {
        (claim["graph_evidence_parent"], claim["source_unit_id"])
        for claim in claims
        if claim["claim_type"] == "regimen_claim"
    }
    for claim in claims:
        if claim["claim_type"] != "atomic_intervention_claim":
            continue
        key = (claim["graph_evidence_parent"], claim["source_unit_id"])
        if key in regimen_units:
            raise ProhibitedInference(
                f"{claim['claim_id']}: claim atomico ricavato dall'unita' del regime"
            )


def summarize_outcomes(associations: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in associations:
        counts[row["association_outcome"]] = counts.get(row["association_outcome"], 0) + 1
    return dict(sorted(counts.items()))
