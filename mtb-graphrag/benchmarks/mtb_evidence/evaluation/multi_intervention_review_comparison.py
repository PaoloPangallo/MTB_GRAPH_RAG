"""Confronto descrittivo fra prima revisione e replica cieca non indipendente.

Le due revisioni hanno annotato gli stessi 13 gruppi e le stesse 28 associazioni
gruppo-intervento. Questo modulo le allinea per chiave deterministica e descrive
dove concordano e dove no.

Il confronto e' **diagnostico**, non una validazione. La replica non e'
indipendente: il prompt che l'ha commissionata nominava la raccomandazione della
prima revisione e il contesto di sessione conteneva gli oggetti dei suoi commit.
Ogni numero prodotto qui e' quindi descrittivo e non sostiene alcuna affermazione
di affidabilita' inter-rater. Le etichette in `METHOD_LABELS` non sono
decorative: i test verificano che compaiano in ogni artefatto.

Il modulo non decide nessun disaccordo. Sceglie soltanto come descriverli.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

COMPARISON_VERSION = "multi-intervention-review-comparison/1.0"

# Etichetta metodologica obbligatoria, ripetuta in ogni artefatto.
METHOD_LABELS = {
    "comparison_type": "first_review_vs_blinded_non_independent_replicate",
    "independent_inter_reviewer_agreement": False,
    "valid_for_external_reliability_claim": False,
    "valid_for_guideline_refinement": True,
    "valid_for_adjudication_preparation": True,
    "descriptive_only_due_to_non_independence": True,
}

# Formulazioni che non possono comparire senza la qualificazione esplicita.
GUARDED_PHRASES = (
    "independent agreement",
    "inter-rater validation",
    "external validation",
    "reviewer convergence",
)

QUALIFIER = "non-independent replicate"


class AlignmentError(RuntimeError):
    """Gli insiemi delle due revisioni non coincidono."""


# --- allineamento -------------------------------------------------------------


def normalize_intervention(label: str) -> str:
    """Normalizzazione conservativa: solo spazi e maiuscole.

    Non fonde forme saline, sinonimi o codici di sviluppo. `BGJ398` resta
    distinto da `infigratinib` e `AUY922` da `luminespib`: l'identita' non
    verificata e' un dato della revisione, non rumore da ripulire.
    """
    return re.sub(r"\s+", " ", str(label)).strip().lower()


def intervention_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["graph_evidence_id"]),
        str(row["source_id"]),
        normalize_intervention(row["intervention"]),
    )


def group_key(row: Mapping[str, Any]) -> tuple[str, str]:
    source = row.get("source_id") or (row.get("source_ids") or [""])[0]
    return (str(row["graph_evidence_id"]), str(source))


def align(
    first: Sequence[Mapping[str, Any]],
    replicate: Sequence[Mapping[str, Any]],
    key,
    *,
    label: str,
) -> list[tuple[Any, Mapping[str, Any], Mapping[str, Any]]]:
    """Allinea per chiave, mai per posizione. Qualunque asimmetria e' fatale."""
    left = {key(row): row for row in first}
    right = {key(row): row for row in replicate}
    if len(left) != len(first) or len(right) != len(replicate):
        raise AlignmentError(f"{label}: chiavi duplicate nell'allineamento")
    only_first = sorted(set(left) - set(right))
    only_replicate = sorted(set(right) - set(left))
    if only_first or only_replicate:
        raise AlignmentError(
            f"{label}: insiemi non coincidenti — solo prima={only_first} solo replica={only_replicate}"
        )
    return [(item, left[item], right[item]) for item in sorted(left)]


# --- esito del claim ----------------------------------------------------------
# Le due revisioni usano vocabolari di materializzazione diversi. La prima non
# ha uno stato `parent_retained`: conserva i 13 parent e crea un figlio per ogni
# risultato separato, incluso quello dell'intervento gia' portato dal parent. La
# replica tiene il parent e crea un figlio solo per gli altri interventi.
#
# Confrontarli alla lettera misurerebbe la differenza di vocabolario. L'asse
# comparabile e' l'esito: per questo intervento esiste un claim, e da dove viene.

CLAIM_OUTCOMES = ("claim_via_new_child", "claim_via_existing_parent", "no_claim")

REPLICATE_OUTCOME = {
    "child_claim_proposed": "claim_via_new_child",
    "parent_retained": "claim_via_existing_parent",
    "not_materialized": "no_claim",
}


def first_review_outcome(
    row: Mapping[str, Any], *, is_parent_intervention: bool, has_simulated_child: bool
) -> str:
    if has_simulated_child:
        return "claim_via_new_child"
    return "claim_via_existing_parent" if is_parent_intervention else "no_claim"


# --- verdetti -----------------------------------------------------------------

COMPARISON_VERDICTS = (
    "exact_agreement",
    "compatible_agreement",
    "granularity_disagreement",
    "documentary_role_disagreement",
    "locator_disagreement",
    "source_unit_disagreement",
    "mapping_disagreement",
    "materialization_disagreement",
    "missing_annotation_first",
    "missing_annotation_replicate",
    "unresolved_alignment",
)

AGREEMENT_VERDICTS = frozenset({"exact_agreement", "compatible_agreement"})

# Coppie di classificazioni che descrivono lo stesso stato documentale con
# etichette diverse. Registrate come dato, non dedotte: la prima revisione
# annota «risultato separato, ma locator del biomarcatore insufficiente»,
# la replica annota «accesso alla fonte insufficiente». Entrambe negano il
# claim e portano allo stesso esito di gruppo.
COMPATIBLE_CLASSIFICATION_PAIRS = (
    ("directly_tested_with_separate_result", "insufficient_source_access"),
)


def classifications_are_compatible(first: str, replicate: str) -> bool:
    return (first, replicate) in COMPATIBLE_CLASSIFICATION_PAIRS or (
        replicate,
        first,
    ) in COMPATIBLE_CLASSIFICATION_PAIRS


def verdict_for(
    *,
    first_classification: str,
    replicate_classification: str,
    first_outcome: str,
    replicate_outcome: str,
    first_locator_insufficient: bool,
    replicate_locator_insufficient: bool,
) -> str:
    """Un solo verdetto primario per associazione, in ordine di precedenza."""
    same_classification = first_classification == replicate_classification
    same_outcome = first_outcome == replicate_outcome

    if same_classification and same_outcome:
        return "exact_agreement"
    if same_classification and not same_outcome:
        return "materialization_disagreement"
    if classifications_are_compatible(first_classification, replicate_classification):
        if same_outcome and first_locator_insufficient == replicate_locator_insufficient:
            return "compatible_agreement"
        return "granularity_disagreement"
    return "documentary_role_disagreement"


# --- locator ------------------------------------------------------------------
# Le due revisioni scrivono il locator in forme diverse: la prima una stringa
# `sezione#ETICHETTA`, la replica un record con citazioni letterali. Confrontare
# le stringhe misurerebbe il formato. L'asse comparabile e' la granularita': il
# locator si ferma alla sezione, o identifica l'unita' dentro il documento?

LOCATOR_GRANULARITY = ("source_only", "section", "sub_document_unit")

# Parole che, nel locator della prima revisione, segnalano un'unita' interna al
# documento e non una semplice sezione.
SUB_UNIT_MARKERS = (
    "patient",
    "figure",
    "table",
    "panel",
    "sentence",
    "clause",
    "paragraph",
    "arm",
    "week",
    "course",
    "exposure",
    "treatment",
    "history",
)

REPLICATE_SUB_UNIT_FIELDS = (
    "patient_id",
    "cell_line",
    "experimental_arm",
    "treatment_line",
    "table",
    "figure",
    "panel",
    "paragraph",
    "abstract_sentence",
)


def locator_detail_text(locator: str) -> str:
    """La parte del locator che sta *oltre* l'etichetta di sezione.

    Il formato della prima revisione e' `sezione#ETICHETTA, dettaglio`, con piu'
    riferimenti separati da `;`. I marcatori vanno cercati solo nel dettaglio:
    l'etichetta di sezione `PATIENTS AND METHODS` contiene la stringa `patient`
    senza identificare alcun paziente, e trattarla come unita' documentale
    gonfierebbe la granularita' di ogni abstract strutturato.
    """
    details = []
    for fragment in str(locator).split(";"):
        fragment = fragment.strip()
        if not fragment:
            continue
        if "#" in fragment:
            after_hash = fragment.split("#", 1)[1]
            if "," in after_hash:
                details.append(after_hash.split(",", 1)[1])
        else:
            details.append(fragment)
    return " ".join(details).lower()


def first_locator_granularity(locator: str) -> str:
    if any(marker in locator_detail_text(locator) for marker in SUB_UNIT_MARKERS):
        return "sub_document_unit"
    if "#" in str(locator):
        return "section"
    return "source_only"


def replicate_locator_granularity(locator: Mapping[str, Any]) -> str:
    if any(str(locator.get(field) or "").strip() for field in REPLICATE_SUB_UNIT_FIELDS):
        return "sub_document_unit"
    if str(locator.get("section") or "").strip():
        return "section"
    return "source_only"


# --- cause dei disaccordi -----------------------------------------------------

DISAGREEMENT_CAUSES = (
    "annotation_guideline_ambiguity",
    "locator_threshold_difference",
    "source_unit_segmentation_difference",
    "intervention_identity_uncertainty",
    "parent_vs_child_policy_difference",
    "regimen_vs_mixed_boundary",
    "biomarker_scope_difference",
    "disease_scope_difference",
    "aggregate_vs_specific_boundary",
    "insufficient_abstract_detail",
    "data_alignment_issue",
    "other",
)

CHILD_DIFFERENCE_REASONS = (
    "parent_intervention_already_represents_result",
    "duplicate_source_unit_support",
    "pending_alias_blocks_child",
    "insufficient_locator",
    "aggregate_result",
    "regimen_component",
    "unsupported_intervention",
    "different_claim_identity",
    "reviewer_policy_difference",
    "unresolved",
)


# --- accordo descrittivo ------------------------------------------------------


def percent_agreement(pairs: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
    items = list(pairs)
    if not items:
        return {"n": 0, "agreements": 0, "percent_agreement": None}
    agreements = sum(1 for left, right in items if left == right)
    return {
        "n": len(items),
        "agreements": agreements,
        "percent_agreement": round(agreements / len(items), 4),
    }


def cohen_kappa(pairs: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
    """Kappa non pesato, con la diagnostica che serve a non fidarsene.

    Il valore viene calcolato ma accompagnato da `interpretable`: con 13 o 28
    item distribuiti su sei-otto categorie molte celle attese restano sotto 5, e
    kappa diventa instabile rispetto alla prevalenza. La soglia e' dichiarata,
    non implicita.
    """
    items = list(pairs)
    total = len(items)
    if total == 0:
        return {"computed": False, "reason": "nessun item da confrontare"}

    categories = sorted({value for pair in items for value in pair})
    left_counts = {name: sum(1 for left, _ in items if left == name) for name in categories}
    right_counts = {name: sum(1 for _, right in items if right == name) for name in categories}

    observed = sum(1 for left, right in items if left == right) / total
    expected = sum(
        (left_counts[name] / total) * (right_counts[name] / total) for name in categories
    )
    if expected >= 1.0:
        return {
            "computed": False,
            "reason": "accordo atteso pari a 1: kappa non definito su una sola categoria",
            "observed_agreement": round(observed, 4),
        }

    min_expected_cell = min(
        (left_counts[name] * right_counts[name]) / total for name in categories
    )
    sparse = min_expected_cell < 5
    return {
        "computed": True,
        "kappa": round((observed - expected) / (1 - expected), 4),
        "observed_agreement": round(observed, 4),
        "expected_agreement": round(expected, 4),
        "n": total,
        "category_count": len(categories),
        "min_expected_cell_count": round(min_expected_cell, 3),
        "sparse_categories": sparse,
        "interpretable": False,
        "interpretation_note": (
            "Valore descrittivo. Non interpretabile come affidabilita' inter-rater: le due"
            " codifiche non sono indipendenti"
            + (
                ", e con questa numerosita' piu' celle attese restano sotto 5, quindi kappa"
                " e' instabile rispetto alla prevalenza."
                if sparse
                else "."
            )
        ),
        "descriptive_only_due_to_non_independence": True,
    }


def confusion_matrix(pairs: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    items = list(pairs)
    categories = sorted({value for pair in items for value in pair})
    matrix = {first: {second: 0 for second in categories} for first in categories}
    for first, second in items:
        matrix[first][second] += 1
    return matrix


# --- consenso provvisorio -----------------------------------------------------


def qualifies_for_provisional_consensus(
    *,
    same_group_decision: bool,
    intervention_verdicts: Sequence[str],
    locator_sufficient: bool,
    pending_mapping_present: bool,
    aggregate_to_specific_risk: bool,
    scope_issue_present: bool,
) -> bool:
    """Il consenso provvisorio e' l'assenza di ogni motivo di dubbio, non la media.

    Basta un mapping pending, un locator insufficiente o un problema di scope
    del biomarcatore perche' il gruppo vada comunque all'adjudicator.
    """
    return (
        same_group_decision
        and all(verdict in AGREEMENT_VERDICTS for verdict in intervention_verdicts)
        and locator_sufficient
        and not pending_mapping_present
        and not aggregate_to_specific_risk
        and not scope_issue_present
    )


def check_guarded_language(text: str) -> list[str]:
    """Le formulazioni forti sono ammesse solo se qualificate nella stessa riga."""
    offenders = []
    for line in text.splitlines():
        lowered = line.lower()
        for phrase in GUARDED_PHRASES:
            if phrase in lowered and QUALIFIER not in lowered:
                offenders.append(line.strip())
    return offenders
