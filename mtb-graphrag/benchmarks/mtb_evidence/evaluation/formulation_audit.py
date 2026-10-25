"""Audit delle forme su tutti i claim attivi, non soltanto su infigratinib.

La contraddizione trovata dall'audit pre-promozione riguardava infigratinib, ma
la regola che la produce non conosce infigratinib: e' una tupla di cinque
suffissi applicata a chiunque. Guardare la sola coppia segnalata avrebbe chiuso
il caso e lasciato la causa.

Il repository contiene tredici claim attivi con un intervento in forma
modificata, e la tabella dei suffissi ne vede dodici. Il tredicesimo —
`neratinib maleate` — resta invisibile perche' `maleate` non e' nella tupla, e
la sua moiety viene percio' trattata come un farmaco estraneo. Le due
popolazioni ricevono trattamenti opposti per una ragione che non e' clinica:
quale suffisso qualcuno ha scritto.

Il modulo registra, per ogni claim con forma, cosa fa oggi il gate e cosa fara'
con il contratto 1.0. Nessuna identita' di claim viene toccata: cambia il
comportamento al retrieval, non cio' che il claim afferma.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.shadow import formulation as FORM
from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    PENDING_ALIASES,
    SALT_FORM_SUFFIXES,
    normalize,
    strip_salt_form,
)

AUDIT_VERSION = "formulation_claim_audit/1.0"

# Codici di sviluppo noti al contratto congelato. Non sono forme: sono nomi
# alternativi della stessa entita', e il loro stato e' deciso dalla terminology
# closure e non da questo modulo.
DEVELOPMENT_CODES = {code for code, _ in PENDING_ALIASES} | {"pd173074", "tae684"}

FORM_KIND_NONE = "no_form_token"


def _current_behaviour(query_literal: str, claim_literal: str) -> str:
    """Cosa fa oggi la regola dei suffissi, ricalcolato e non ricordato."""
    left, right = normalize(query_literal), normalize(claim_literal)
    if left == right:
        return "exact_atomic_intervention"
    if strip_salt_form(left) == strip_salt_form(right):
        return "normalized_atomic_intervention"
    return "incompatible"


def _proposed_behaviour(query_literal: str, claim_literal: str) -> str:
    return FORM.resolve(query_literal, claim_literal).relation_type


def claim_form_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Una riga per ogni claim attivo il cui intervento porta una forma o un codice.

    La domanda posta a ciascuno e' sempre la stessa: se qualcuno cercasse la
    moiety nuda, cosa succederebbe oggi e cosa succedera' dopo.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        literals = _claim_literals(record)
        for literal in literals:
            tokens = FORM.form_tokens(literal)
            moiety_candidate = FORM.candidate_active_moiety(literal)
            is_development_code = normalize(literal) in DEVELOPMENT_CODES
            if not tokens and not is_development_code:
                continue
            form_kind, _ = FORM.form_of(literal)
            probe = moiety_candidate if tokens else literal
            current = _current_behaviour(probe, literal)
            proposed = _proposed_behaviour(probe, literal)
            relation = FORM.resolve(probe, literal)
            rows.append(
                {
                    "active_moiety_candidate": moiety_candidate,
                    "authoritative_support": relation.authoritative_source or None,
                    "claim_id": record["claim_id"],
                    "claim_id_impact": "unchanged",
                    "claim_type": record["claim_type"],
                    "current_match_behavior": current,
                    "current_reaches_primary": current
                    in ("exact_atomic_intervention", "normalized_atomic_intervention"),
                    "form_kind": form_kind if tokens else FORM_KIND_NONE,
                    "form_tokens": list(tokens),
                    "graph_evidence_id": record["graph_evidence_id"],
                    "is_development_code": is_development_code,
                    "parent_id": record["parent_id"],
                    "proposed_match_behavior": proposed,
                    "proposed_reaches_primary": proposed in FORM.EXACT_FORM_RELATIONS,
                    "probe_literal": probe,
                    "relation_status": relation.relation_status,
                    "retrieval_impact": _retrieval_impact(current, proposed),
                    "seen_by_current_suffix_table": bool(
                        tokens
                        and any(
                            normalize(literal).endswith(suffix)
                            for suffix in SALT_FORM_SUFFIXES
                        )
                    ),
                    "source_literal": literal,
                }
            )
    return sorted(rows, key=lambda row: (row["claim_id"], row["source_literal"]))


def _claim_literals(record: Mapping[str, Any]) -> list[str]:
    if record["claim_type"] == "atomic_intervention_claim":
        return [str(record.get("canonical_intervention") or record.get("intervention"))]
    if record["claim_type"] == "regimen_claim":
        return [str(item) for item in (record.get("regimen_components") or ())]
    if record["claim_type"] == "aggregate_intervention_claim":
        members = list(record.get("aggregate_members_literal") or ())
        members += list(record.get("canonical_members") or ())
        return sorted({str(item) for item in members})
    return []


def _retrieval_impact(current: str, proposed: str) -> str:
    """Come cambia la raggiungibilita' dalla moiety nuda."""
    was_primary = current in ("exact_atomic_intervention", "normalized_atomic_intervention")
    will_be_primary = proposed in FORM.EXACT_FORM_RELATIONS
    if was_primary and not will_be_primary:
        return "leaves_primary_bucket"
    if not was_primary and will_be_primary:
        return "enters_primary_bucket"
    if current == "incompatible" and proposed in (
        FORM.UNRESOLVED_FORMULATION_RELATION,
        *sorted(FORM.VERIFIED_DIFFERENT_FORM_RELATIONS),
    ):
        return "becomes_visible_instead_of_rejected"
    return "unchanged"


# --- revisione della coppia segnalata dall'audit ------------------------------

REVIEWED_PAIRS = (
    {
        "active_moiety": "infigratinib",
        "authoritative_source": "DGIdb su NCIt e RxNorm, evidence EV-BGJ398-06",
        "form_kind": FORM.FORM_SALT,
        "form_label": "infigratinib phosphate",
        "new_decision": FORM.VERIFIED_SALT_OF_ACTIVE_MOIETY,
        "new_bucket": FORM.WARNING,
        "present_in_graph": False,
        "previous_behaviour": "incompatible",
        "previous_bucket": FORM.REJECTED,
        "relation_status": FORM.STATUS_VERIFIED,
        "rule_origin": (
            "assenza di 'phosphate' dalla tupla SALT_FORM_SUFFIXES del contratto "
            "claim-type-retrieval-contract/1.0"
        ),
        "why": (
            "E' l'unica coppia di forme del repository per cui esiste una fonte "
            "autorevole, e la regola in vigore la respinge come farmaco estraneo. "
            "Il sale ha concept id proprio (ncit:C175088), distinto dalla moiety "
            "(rxcui:2550729): la relazione esiste, ed e' una relazione di "
            "diversita'."
        ),
    },
    {
        "active_moiety": "infigratinib",
        "authoritative_source": None,
        "form_kind": FORM.FORM_SALT,
        "form_label": "infigratinib hydrochloride",
        "new_decision": FORM.UNRESOLVED_FORMULATION_RELATION,
        "new_bucket": FORM.AUDIT,
        "present_in_graph": False,
        "previous_behaviour": "normalized_atomic_intervention",
        "previous_bucket": FORM.PRIMARY,
        "relation_status": FORM.STATUS_UNRESOLVED,
        "rule_origin": (
            "presenza di 'hydrochloride' nella tupla SALT_FORM_SUFFIXES del "
            "contratto claim-type-retrieval-contract/1.0"
        ),
        "why": (
            "Nessuna fonte lega questa forma alla moiety, e nessun record del "
            "grafo la contiene. Diventava primaria per il solo fatto che il suo "
            "suffisso era stato scritto in una tupla. Senza prove la relazione "
            "resta irrisolta: non fusa e non respinta, ma visibile in audit."
        ),
    },
)


def reviewed_pairs() -> list[dict[str, Any]]:
    """La revisione esplicita della coppia che ha generato il finding.

    Le due forme non vengono decise per simmetria ne' per presenza nel grafo.
    Ricevono esiti diversi perche' le prove disponibili sono diverse, ed e'
    questa la differenza che la tabella dei suffissi non sapeva rappresentare.
    """
    return [
        row | {"decided_by_presence_in_graph": False, "fused_with_moiety": False}
        for row in REVIEWED_PAIRS
    ]


def audit(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = claim_form_rows(records)
    salt_rows = [row for row in rows if row["form_kind"] == FORM.FORM_SALT]
    impacts = Counter(row["retrieval_impact"] for row in rows)
    return {
        "audit_version": AUDIT_VERSION,
        "claim_identities_changed": 0,
        "claims_with_form_or_code": len(rows),
        "current_suffix_table": list(SALT_FORM_SUFFIXES),
        "development_code_literals": sorted(
            {row["source_literal"] for row in rows if row["is_development_code"]}
        ),
        "distinct_form_literals": sorted({row["source_literal"] for row in salt_rows}),
        "forms_invisible_to_current_suffix_table": sorted(
            {
                row["source_literal"]
                for row in salt_rows
                if not row["seen_by_current_suffix_table"]
            }
        ),
        "retrieval_impacts": dict(sorted(impacts.items())),
        "reviewed_pairs": reviewed_pairs(),
        "salt_form_claims": len(salt_rows),
        "salt_form_claims_leaving_primary": sorted(
            {
                row["claim_id"]
                for row in salt_rows
                if row["retrieval_impact"] == "leaves_primary_bucket"
            }
        ),
        "verified_form_relations": len(FORM.VERIFIED_FORMULATION_REGISTRY),
    }


__all__ = [
    "AUDIT_VERSION",
    "DEVELOPMENT_CODES",
    "REVIEWED_PAIRS",
    "audit",
    "claim_form_rows",
    "reviewed_pairs",
]
