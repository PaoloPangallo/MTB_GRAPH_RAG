"""Seconda revisione documentale, in cieco, dei gruppi multi-intervento.

Un `graph_evidence_id` puo' portare piu' interventi candidati. Se quegli
interventi meritino uno statement figlio e' una domanda **documentale**, non di
schema: o la fonte attribuisce un risultato separato a ciascun farmaco, oppure
no. Questo modulo porta il vocabolario di una seconda passata su quella stessa
domanda, condotta a partire dai soli packet ciechi.

Il tetto di cio' che questa fase puo' produrre e' l'annotazione documentale e la
decisione per gruppo. Non produce una raccomandazione architetturale, non
confronta con nessun'altra revisione, non fa adjudication e non promuove nulla a
gold: `propagation_policy = prototype_only`, `hard_filterable = false`,
`final_evaluable = false`.

Il modulo non importa nulla della prima revisione. La cecita' non e' una
convenzione ma un invariante verificabile: `DENIED_PATH_FRAGMENTS` elenca cio'
che non puo' essere aperto, `read_tracked` registra ogni lettura e solleva su
violazione, e il log risultante e' un artefatto della revisione.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REVIEW_VERSION = "multi-intervention-second-review/1.0"
PACKET_SCHEMA_VERSION = "multi-intervention-source-review/1.0"

# --- perimetro ----------------------------------------------------------------
# I 13 gruppi sono dichiarati, non contati: il controllo confronta l'insieme
# derivato dalla directory con questo, cosi' un packet aggiunto o rimosso fa
# fallire il perimetro invece di scorrere silenziosamente in un conteggio.
EXPECTED_PACKET_IDS = (
    "MI-B-1c375f91d580512a",
    "MI-B-3ded61139bc74e60",
    "MI-B-72b36cde2fff1311",
    "MI-B-8274e1f9586ef644",
    "MI-B-83c70396946a191d",
    "MI-B-86f8143c879081d2",
    "MI-B-92bfd4c87e04cbb2",
    "MI-B-95447460cf63aa6f",
    "MI-B-b4e82c2009b6a061",
    "MI-B-c9174014bdf40550",
    "MI-B-cd69de17ac73dc47",
    "MI-B-f17288721b33657d",
    "MI-B-f8fefcc976a5eaa9",
)


class ScopeMismatch(RuntimeError):
    """Il perimetro derivato non coincide con quello dichiarato."""


class BlindnessViolation(RuntimeError):
    """E' stata tentata la lettura di un artefatto della prima revisione."""


class LocatorInsufficient(RuntimeError):
    """Il locator non identifica un'unita' documentale oltre alla fonte."""


class ProhibitedInference(RuntimeError):
    """La decisione trasformerebbe la fonte in qualcosa che non dice."""


# --- classificazione per intervento -------------------------------------------

INTERVENTION_CATEGORIES = (
    "directly_tested_with_separate_result",
    "directly_tested_in_shared_aggregate_result",
    "directly_tested_in_combination_regimen",
    "comparator_only",
    "mentioned_background_only",
    "cited_prior_evidence_only",
    "drug_class_member_not_individually_tested",
    "development_code_verified_same_intervention",
    "possible_alias_not_verified",
    "result_not_attributable_to_specific_intervention",
    "conflicting_results_across_units",
    "intervention_not_found_in_source",
    "insufficient_source_access",
    "unresolved",
)

# Solo un risultato separato — o un codice di sviluppo verificato come lo stesso
# intervento — puo' diventare un claim autonomo. Ogni altra categoria descrive
# una ragione per cui il claim non esiste nella fonte.
MATERIALIZABLE_CATEGORIES = frozenset(
    {
        "directly_tested_with_separate_result",
        "development_code_verified_same_intervention",
    }
)

AGGREGATE_CATEGORIES = frozenset(
    {
        "directly_tested_in_shared_aggregate_result",
        "result_not_attributable_to_specific_intervention",
        "drug_class_member_not_individually_tested",
    }
)

REGIMEN_CATEGORIES = frozenset({"directly_tested_in_combination_regimen"})

MENTION_CATEGORIES = frozenset(
    {
        "comparator_only",
        "mentioned_background_only",
        "cited_prior_evidence_only",
        "intervention_not_found_in_source",
    }
)

PENDING_ALIAS_CATEGORIES = frozenset({"possible_alias_not_verified"})

INSUFFICIENT_CATEGORIES = frozenset(
    {
        "insufficient_source_access",
        "conflicting_results_across_units",
        "unresolved",
    }
)

# --- decisione per gruppo -----------------------------------------------------

GROUP_DECISIONS = (
    "atomic_children_supported",
    "aggregate_parent_only",
    "combination_regimen_required",
    "verified_alias_merge",
    "mixed_parent_and_children",
    "should_not_materialize_missing_interventions",
    "insufficient_for_atomicity_decision",
)

# Decisioni che, per definizione, non possono generare uno statement figlio.
NO_CHILD_DECISIONS = frozenset(
    {
        "aggregate_parent_only",
        "combination_regimen_required",
        "should_not_materialize_missing_interventions",
        "insufficient_for_atomicity_decision",
    }
)

MATERIALIZATION_STATES = (
    "parent_retained",
    "child_claim_proposed",
    "not_materialized",
)

EVIDENCE_SETTINGS = ("clinical", "preclinical")

# --- alias --------------------------------------------------------------------
# Un mapping vale come verificato solo se gia' approvato localmente oppure se la
# fonte stessa identifica i due termini come lo stesso intervento. Il registro
# locale (`v3/first_review/intervention_mappings.jsonl`) al momento non contiene
# alcun mapping approvato: entrambe le voci sono
# `requires_source_or_terminology_verification`.
ALIAS_STATUSES = (
    "literal_match",
    "salt_form_same_active_moiety",
    "verified_in_source",
    "locally_approved_mapping",
    "pending_not_verified",
    "absent_from_source",
)

VERIFIED_ALIAS_STATUSES = frozenset(
    {
        "literal_match",
        "salt_form_same_active_moiety",
        "verified_in_source",
        "locally_approved_mapping",
    }
)

# Codici di sviluppo che non possono essere promossi automaticamente al nome
# generico. Elencati per rendere il divieto un controllo e non una convenzione.
PENDING_DEVELOPMENT_CODE_MAPPINGS = (
    ("AUY922", "luminespib"),
    ("BGJ398", "infigratinib"),
    ("CH5424802", "alectinib"),
    ("17-AAG", "tanespimycin"),
)

# --- locator ------------------------------------------------------------------
# Un locator deve identificare un'unita' documentale *oltre* alla fonte. Il solo
# PMID non e' un locator: identifica il documento, non il punto in cui il
# risultato e' affermato.
LOCATOR_UNIT_FIELDS = (
    "page",
    "section",
    "table",
    "figure",
    "panel",
    "paragraph",
    "abstract_sentence",
    "patient_id",
    "cell_line",
    "experimental_arm",
    "treatment_line",
)

LOCATOR_STATUSES = ("sufficient", "insufficient_for_claim", "unavailable")

SOURCE_ACCESS_STATUSES = ("full_text", "abstract_only", "unavailable")


def locator_is_sufficient(locator: Mapping[str, Any]) -> bool:
    """Vero se il locator identifica un'unita' documentale oltre alla fonte."""
    if not locator.get("source_id"):
        return False
    return any(str(locator.get(field) or "").strip() for field in LOCATOR_UNIT_FIELDS)


def check_locator(locator: Mapping[str, Any]) -> None:
    if not locator_is_sufficient(locator):
        raise LocatorInsufficient(
            "il locator non identifica alcuna unita' documentale oltre alla fonte: "
            f"{locator.get('source_id')!r}"
        )


# --- cecita' ------------------------------------------------------------------
# Frammenti di path che questa revisione non puo' leggere. Il confronto e' su
# path normalizzato con separatori POSIX, cosi' vale su Windows come altrove.
DENIED_PATH_FRAGMENTS = (
    "group_atomicity_decisions",
    "intervention_level_annotations",
    "architectural_recommendation",
    "post_review_schema_simulation",
    "multi_intervention_source_review.md",
    "atomicity_decision_report",
    "adapter_migration_readiness",
    "multi_intervention_adapter_review",
    "test_multi_intervention_source_review",
    "scripts/multi_intervention_source_review",
    "provisional_gold",
    "snapshot_gold",
    "clinical_gold",
    "/gold/",
    "_gold.jsonl",
)


def normalized(path: Path | str) -> str:
    return str(path).replace("\\", "/").lower()


def is_denied(path: Path | str) -> bool:
    text = normalized(path)
    return any(fragment in text for fragment in DENIED_PATH_FRAGMENTS)


def check_not_denied(path: Path | str) -> None:
    if is_denied(path):
        raise BlindnessViolation(f"lettura vietata in seconda revisione: {path}")


class AccessLog:
    """Registra ogni lettura e rifiuta i path della prima revisione.

    Il log e' un artefatto: `allowed_file_access_log.jsonl` deve poter essere
    riletto da un test che verifica che nessun path vietato vi compaia.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.entries: list[dict[str, Any]] = []

    def _relative(self, path: Path) -> str:
        try:
            return normalized(path.resolve().relative_to(self.repo_root))
        except ValueError:
            return normalized(path.resolve())

    def record(self, path: Path, *, purpose: str, sha256: str | None = None) -> None:
        check_not_denied(path)
        self.entries.append(
            {
                "access_kind": "read",
                "logical_path": self._relative(path),
                "purpose": purpose,
                "sha256": sha256,
            }
        )

    def note(self, *, logical_path: str, purpose: str, access_kind: str) -> None:
        check_not_denied(logical_path)
        self.entries.append(
            {
                "access_kind": access_kind,
                "logical_path": normalized(logical_path),
                "purpose": purpose,
                "sha256": None,
            }
        )

    def read_text(self, path: Path, *, purpose: str) -> str:
        check_not_denied(path)
        payload = path.read_bytes()
        self.record(path, purpose=purpose, sha256=sha256_bytes(payload))
        return payload.decode("utf-8")

    def sorted_entries(self) -> list[dict[str, Any]]:
        return sorted(
            self.entries,
            key=lambda row: (row["logical_path"], row["access_kind"], row["purpose"]),
        )


# --- hashing e determinismo ---------------------------------------------------


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def aggregate_hash(pairs: Iterable[tuple[str, str]]) -> str:
    """Hash aggregato sull'elenco ordinato `id:hash`, non sui byte concatenati.

    Ordinare per identificatore rende l'aggregato indipendente dall'ordine in
    cui i packet vengono presentati al revisore, che e' esattamente la proprieta'
    che il test sull'ordine invertito verifica.
    """
    joined = "\n".join(f"{key}:{value}" for key, value in sorted(pairs))
    return sha256_text(joined)


def canonical_dumps(payload: Any) -> str:
    """JSON deterministico: chiavi ordinate, niente spazi variabili."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def canonical_jsonl(rows: Sequence[Mapping[str, Any]], *, key: str | Sequence[str]) -> str:
    """JSONL deterministico, ordinato per chiave dichiarata."""
    keys = (key,) if isinstance(key, str) else tuple(key)

    def sort_key(row: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(str(row.get(field) or "") for field in keys)

    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True) for row in sorted(rows, key=sort_key)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


# --- validazione delle annotazioni --------------------------------------------

REQUIRED_ANNOTATION_FIELDS = (
    "alias_status",
    "biomarker",
    "blind_annotation_id",
    "claim_direction",
    "claim_polarity",
    "classification",
    "confidence",
    "disease",
    "evidence_setting",
    "graph_evidence_id",
    "intervention",
    "is_current_statement_intervention",
    "locator",
    "locator_status",
    "materialization",
    "observed_direction",
    "observed_polarity",
    "paraphrased_result",
    "population_model",
    "reviewer_note",
    "source_access_status",
    "source_id",
    "source_literal_term",
    "source_unit_id",
)

CONFIDENCE_LEVELS = ("high", "medium", "low")


def check_annotation(row: Mapping[str, Any]) -> None:
    """Un'annotazione e' valida solo se completa, coerente e non inferenziale."""
    missing = [field for field in REQUIRED_ANNOTATION_FIELDS if field not in row]
    if missing:
        raise ScopeMismatch(f"annotazione incompleta {row.get('blind_annotation_id')}: {missing}")

    if row["classification"] not in INTERVENTION_CATEGORIES:
        raise ScopeMismatch(f"categoria sconosciuta: {row['classification']}")
    if row["materialization"] not in MATERIALIZATION_STATES:
        raise ScopeMismatch(f"stato di materializzazione sconosciuto: {row['materialization']}")
    if row["locator_status"] not in LOCATOR_STATUSES:
        raise ScopeMismatch(f"stato di locator sconosciuto: {row['locator_status']}")
    if row["alias_status"] not in ALIAS_STATUSES:
        raise ScopeMismatch(f"stato di alias sconosciuto: {row['alias_status']}")
    if row["confidence"] not in CONFIDENCE_LEVELS:
        raise ScopeMismatch(f"confidence sconosciuta: {row['confidence']}")
    if row["evidence_setting"] not in EVIDENCE_SETTINGS:
        raise ScopeMismatch(f"setting sconosciuto: {row['evidence_setting']}")

    if not row.get("source_unit_id"):
        raise ScopeMismatch(
            f"classificazione senza source unit: {row['blind_annotation_id']}/{row['intervention']}"
        )

    declared_sufficient = row["locator_status"] == "sufficient"
    if declared_sufficient and not locator_is_sufficient(row["locator"]):
        raise LocatorInsufficient(
            f"locator dichiarato sufficiente ma privo di unita': "
            f"{row['blind_annotation_id']}/{row['intervention']}"
        )

    if row["classification"] in PENDING_ALIAS_CATEGORIES and row["alias_status"] != "pending_not_verified":
        raise ProhibitedInference(
            f"alias non verificato con stato {row['alias_status']}: {row['intervention']}"
        )

    if row["materialization"] == "child_claim_proposed":
        _check_child_is_supported(row)


def _check_child_is_supported(row: Mapping[str, Any]) -> None:
    """Un figlio esiste solo se la fonte lo sostiene per intero."""
    name = f"{row['blind_annotation_id']}/{row['intervention']}"
    if row["classification"] in AGGREGATE_CATEGORIES:
        raise ProhibitedInference(f"aggregate_to_specific: {name}")
    if row["classification"] in REGIMEN_CATEGORIES:
        raise ProhibitedInference(f"regimen splittato in componenti: {name}")
    if row["classification"] in MENTION_CATEGORIES:
        raise ProhibitedInference(f"mention_to_tested: {name}")
    if row["classification"] in PENDING_ALIAS_CATEGORIES:
        raise ProhibitedInference(f"pending_mapping_to_verified_alias: {name}")
    if row["classification"] in INSUFFICIENT_CATEGORIES:
        raise ProhibitedInference(f"claim da fonte insufficiente: {name}")
    if row["classification"] not in MATERIALIZABLE_CATEGORIES:
        raise ProhibitedInference(f"categoria non materializzabile: {name}")
    if row["alias_status"] not in VERIFIED_ALIAS_STATUSES:
        raise ProhibitedInference(f"alias non verificato promosso a claim: {name}")
    if row["locator_status"] != "sufficient":
        raise LocatorInsufficient(f"figlio senza locator sufficiente: {name}")
    check_locator(row["locator"])
    if row["observed_direction"] != row["claim_direction"]:
        raise ProhibitedInference(
            f"direzione osservata diversa da quella del claim: {name}"
        )
    if row["observed_polarity"] != row["claim_polarity"]:
        raise ProhibitedInference(f"polarita' osservata diversa da quella del claim: {name}")


def check_group_decision(decision: str, rows: Sequence[Mapping[str, Any]]) -> None:
    """La decisione di gruppo deve essere sostenuta dalle sue annotazioni."""
    if decision not in GROUP_DECISIONS:
        raise ScopeMismatch(f"decisione di gruppo sconosciuta: {decision}")
    if not rows:
        raise ScopeMismatch(f"decisione senza annotazioni: {decision}")

    group = rows[0]["blind_annotation_id"]
    parents = [row for row in rows if row["materialization"] == "parent_retained"]
    if len(parents) != 1:
        raise ScopeMismatch(f"{group}: attesa una sola annotazione parent_retained, trovate {len(parents)}")
    if not parents[0]["is_current_statement_intervention"]:
        raise ScopeMismatch(f"{group}: il parent trattenuto non e' l'intervento dello statement")

    children = [row for row in rows if row["materialization"] == "child_claim_proposed"]

    if decision in NO_CHILD_DECISIONS and children:
        raise ProhibitedInference(
            f"{group}: {decision} non puo' proporre figli ({len(children)} proposti)"
        )

    if decision == "atomic_children_supported":
        for row in rows:
            if row["materialization"] == "not_materialized":
                raise ProhibitedInference(
                    f"{group}: atomic_children_supported con un intervento non materializzabile "
                    f"({row['intervention']})"
                )
            if row["locator_status"] != "sufficient":
                raise LocatorInsufficient(
                    f"{group}: atomic_children_supported con locator insufficiente "
                    f"({row['intervention']})"
                )
        if not children:
            raise ScopeMismatch(f"{group}: atomic_children_supported senza figli proposti")

    if decision == "mixed_parent_and_children":
        # «Solo alcuni interventi hanno risultati autonomi»: la condizione e'
        # sull'autonomia del risultato, non sul fatto che l'intervento autonomo
        # sia un figlio. Un gruppo in cui solo il parent ha un risultato di
        # braccio e l'altro intervento esiste solo dentro il regime e' misto
        # anche se non propone alcun figlio.
        autonomous = [
            row
            for row in rows
            if row["classification"] in MATERIALIZABLE_CATEGORIES
            and row["locator_status"] == "sufficient"
        ]
        if not autonomous:
            raise ScopeMismatch(
                f"{group}: mixed_parent_and_children senza alcun risultato autonomo"
            )
        if not any(row["materialization"] == "not_materialized" for row in rows):
            raise ScopeMismatch(
                f"{group}: mixed_parent_and_children senza interventi non materializzati"
            )

    if decision == "verified_alias_merge":
        if any(row["alias_status"] == "pending_not_verified" for row in rows):
            raise ProhibitedInference(f"{group}: merge di alias con mapping pending")


def check_no_pending_mapping_promoted(rows: Sequence[Mapping[str, Any]]) -> None:
    """Nessun codice di sviluppo pending puo' comparire come alias verificato."""
    pending_targets = {generic.lower() for _, generic in PENDING_DEVELOPMENT_CODE_MAPPINGS}
    for row in rows:
        intervention = str(row["intervention"]).lower()
        if not any(target in intervention for target in pending_targets):
            continue
        literal = str(row.get("source_literal_term") or "").upper()
        codes = {code.upper() for code, _ in PENDING_DEVELOPMENT_CODE_MAPPINGS}
        if literal in codes and row["alias_status"] in VERIFIED_ALIAS_STATUSES:
            raise ProhibitedInference(
                "pending_mapping_to_verified_alias: "
                f"{row['blind_annotation_id']}/{row['intervention']} da {literal}"
            )


# --- lettura dei packet -------------------------------------------------------


def packet_paths(directory: Path) -> list[Path]:
    return sorted(directory.glob("MI-B-*.json"))


def check_packet_scope(packet_ids: Sequence[str]) -> None:
    derived = sorted(packet_ids)
    expected = sorted(EXPECTED_PACKET_IDS)
    if derived != expected:
        missing = sorted(set(expected) - set(derived))
        extra = sorted(set(derived) - set(expected))
        raise ScopeMismatch(f"perimetro packet divergente: mancanti={missing} in piu'={extra}")


ABSTRACT_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")


def sentence_index(source_text: str, needle: str) -> int | None:
    """Indice 1-based della frase che contiene `needle`, per il locator."""
    for index, sentence in enumerate(ABSTRACT_SENTENCE_SPLIT.split(source_text.strip()), start=1):
        if needle in sentence:
            return index
    return None
