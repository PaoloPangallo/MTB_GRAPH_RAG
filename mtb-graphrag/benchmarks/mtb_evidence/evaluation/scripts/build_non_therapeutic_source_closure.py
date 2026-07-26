"""Chiude le due questioni documentali aperte sui record non terapeutici.

Parte A: `evidence:347` / `PMID:24662454`. Parte B: prima revisione umana della
source unit `PU-PMID-24122810-cohort-1` che sostiene i due claim diagnostici.

Non modifica il corpus operativo, l'adapter, il retriever, lo scoring, il
repository shadow 1.0 o 1.1. Non promuove nulla. Non legge il gold. Non
ricostruisce contenuto mancante: dove il full text non e' recuperabile, lo
dichiara e si ferma.

Deterministico: output ordinati per chiave dichiarata; `--reverse-input-order`
inverte gli ingressi e il risultato deve restare byte-identico.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
CORPUS = V3 / "qualification_corpus_v2"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
CURATION = V3 / "priority_curation"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "non_therapeutic_source_closure"

REVIEW_VERSION = "non-therapeutic-source-closure/1.0"

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/active_source_profile_units.jsonl",
)

# Campi della decisione del primo reviewer che non devono comparire nei packet
# di seconda revisione. Il packet porta il materiale, non la conclusione.
BLINDED_FIELDS = (
    "decision",
    "decisions",
    "supported_content",
    "required_narrowing",
    "content_not_attributable",
    "limitation_codes",
    "reason_codes",
    "can_become_final",
    "final_blocked_by",
    "locator_status",
    "prognostic_direction_supported",
    "predictive_claim_proposal_supported",
    "review_status",
    "findings",
    "limitations",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build(reverse: bool = False) -> dict[str, str]:
    review = load_json(DATA / "source_closure_v1.json")
    access = list(review["source_access"])
    claim_reviews = list(review["diagnostic_claim_reviews"])
    if reverse:
        access = list(reversed(access))
        claim_reviews = list(reversed(claim_reviews))

    artifacts: dict[str, str] = {}
    artifacts["review_scope.json"] = canonical_dumps(_scope(review))
    artifacts["source_access_inventory.jsonl"] = canonical_jsonl(
        [_access_row(a) for a in access], key="source_id"
    )
    artifacts["source_file_hashes.json"] = canonical_dumps(_file_hashes(access))
    artifacts["evidence_347_source_review.json"] = canonical_dumps(
        _evidence_347_review(review)
    )
    artifacts["evidence_347_claim_proposal.json"] = canonical_dumps(
        _evidence_347_proposal(review)
    )
    artifacts["pmid_24122810_source_unit_review.json"] = canonical_dumps(
        _source_unit_review(review)
    )
    artifacts["diagnostic_claim_reviews.jsonl"] = canonical_jsonl(
        claim_reviews, key="graph_evidence_id"
    )
    artifacts["locator_audit.jsonl"] = canonical_jsonl(
        _locator_audit(review, claim_reviews), key="locator_id"
    )
    artifacts["source_limitations.jsonl"] = canonical_jsonl(
        _limitations(review, claim_reviews), key=["scope_id", "code"]
    )

    for name, payload in sorted(_second_review_packets(review, claim_reviews).items()):
        artifacts[f"second_review_packets/{name}"] = canonical_dumps(payload)

    simulation = _shadow_simulation(review, claim_reviews)
    artifacts["shadow_update_simulation.json"] = canonical_dumps(simulation)
    artifacts["review_manifest.json"] = canonical_dumps(
        _manifest(artifacts, review, claim_reviews, simulation)
    )
    return artifacts


# --- scope e accesso ----------------------------------------------------------


def _scope(review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "review_version": REVIEW_VERSION,
        "reviewer_role": review["reviewer_role"],
        "review_independence": review["review_independence"],
        "review_date": review["review_date"],
        "questions_closed": [
            {
                "question": "A",
                "graph_evidence_id": "evidence:347",
                "source_id": "PMID:24662454",
                "goal": "stabilire se la fonte consenta una proposizione terapeutica con ruolo predittivo, o confermi soltanto un disegno esplorativo non materializzabile, o mantenga il caso unresolved, o rifiuti la direzione prognostic del grafo",
            },
            {
                "question": "B",
                "source_unit_id": "PU-PMID-24122810-cohort-1",
                "source_id": "PMID:24122810",
                "goal": "completare la prima revisione umana della source unit e verificare che i due DiagnosticClaim siano realmente sostenuti e correttamente limitati",
                "claims_reviewed": ["evidence:1846", "evidence:1847"],
            },
        ],
        "materials_priority_order": [
            "full_text_locale",
            "supplementi_locali",
            "versione_open_access",
            "repository_istituzionale_o_archivio_ufficiale",
            "abstract_indicizzato",
            "metadati_locali",
        ],
        "secondary_sources_used": False,
        "secondary_sources_policy": "blog, pagine commerciali e riassunti secondari non sono ammessi come fonte documentale primaria",
        "gold_used": review["gold_used"],
        "content_reconstructed": False,
        "operational_corpus_modified": False,
        "shadow_repository_modified": False,
        "new_claim_types_introduced": 0,
        "terminology_mappings_promoted": 0,
        "disease_hierarchy_modified": False,
    }


def _access_row(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_id": entry["source_id"],
        "doi": entry["doi"],
        "journal": entry["journal"],
        "publication_date": entry["publication_date"],
        "title": entry["title"],
        "source_access_status": entry["source_access_status"],
        "source_text_kind": entry["source_text_kind"],
        "material_used": entry["material_used"],
        "access_attempts": [dict(a) for a in entry["attempts"]],
        "attempts_made": len(entry["attempts"]),
        "highest_priority_succeeded": min(
            (a["priority"] for a in entry["attempts"] if a["outcome"] == "available"),
            default=None,
        ),
        "locator": next(
            a["locator"] for a in entry["attempts"] if a["outcome"] == "available"
        ),
        "access_date": entry["abstract_access_date"],
        "retrieved_from": entry["abstract_retrieved_from"],
        "file_sha256": entry["abstract_sha256"],
        "licence_or_accessibility": entry["licence_or_accessibility"],
        "completeness": entry["completeness"],
        "missing_sections": list(entry["missing_sections"]),
        "secondary_sources_used": entry["secondary_sources_used"],
        "content_reconstructed": entry["content_reconstructed"],
    }


def _file_hashes(access: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Hash del materiale effettivamente usato, verificato contro la cache locale."""
    cache = {
        row["pmid"]: row
        for row in load_jsonl(CURATION / "source_abstract_cache.jsonl")
    }
    entries = {}
    for entry in sorted(access, key=lambda a: a["source_id"]):
        pmid = entry["source_id"].split(":")[1]
        cached = cache[pmid]
        recomputed = sha256_text(cached["abstract_text"])
        entries[entry["source_id"]] = {
            "material": "abstract",
            "declared_sha256": entry["abstract_sha256"],
            "recomputed_sha256": recomputed,
            "hash_matches": recomputed == entry["abstract_sha256"],
            "length": entry["abstract_length"],
            "sections": list(entry["abstract_sections"]),
            "retrieved_from": entry["abstract_retrieved_from"],
            "access_date": entry["abstract_access_date"],
            "full_text_file_present": False,
            "full_text_sha256": None,
            "supplement_present": False,
        }
    return {
        "review_version": REVIEW_VERSION,
        "note": (
            "Nessun file di full text e' stato acquisito, quindi nessun hash di full "
            "text esiste. Gli hash qui sono quelli del materiale realmente letto — "
            "l'abstract indicizzato — ricalcolati dalla cache locale e confrontati con "
            "quelli dichiarati."
        ),
        "entries": entries,
        "all_hashes_match": all(e["hash_matches"] for e in entries.values()),
    }


# --- parte A ------------------------------------------------------------------


def _evidence_347_review(review: Mapping[str, Any]) -> dict[str, Any]:
    record = review["evidence_347"]
    access = next(
        a for a in review["source_access"] if a["source_id"] == record["source_id"]
    )
    return {
        "review_version": REVIEW_VERSION,
        "graph_evidence_id": record["graph_evidence_id"],
        "legacy_statement_id": record["legacy_statement_id"],
        "source_id": record["source_id"],
        "source_access_status": access["source_access_status"],
        "material_used": access["material_used"],
        "material_sha256": access["abstract_sha256"],
        "graph_assertion": {
            "direction": record["graph_direction"],
            "biomarker": record["graph_biomarker"],
            "disease": record["graph_disease"],
            "intervention": record["graph_intervention"],
        },
        "questions": record["questions"],
        "decisions": list(record["decisions"]),
        "prognostic_direction_supported": record["prognostic_direction_supported"],
        "predictive_claim_proposal_supported": record["predictive_claim_proposal_supported"],
        "claim_created": record["claim_created"],
        "intervention_invented": record["intervention_invented"],
        "reason_codes": list(record["reason_codes"]),
        "locator_status": record["locator_status"],
        "legacy_statement_status": record["legacy_statement_status"],
        "legacy_statement_status_changed_by_this_phase": record[
            "legacy_statement_status_changed_by_this_phase"
        ],
        "content_reconstructed": False,
        "gold_used": False,
    }


def _evidence_347_proposal(review: Mapping[str, Any]) -> dict[str, Any]:
    """La proposta di claim che *non* viene fatta, e perche'.

    L'artefatto esiste anche quando la proposta e' assente: registrare il vuoto
    e' cio' che distingue una decisione da una dimenticanza.
    """
    record = review["evidence_347"]
    return {
        "review_version": REVIEW_VERSION,
        "graph_evidence_id": "evidence:347",
        "proposal_made": False,
        "proposed_claim": None,
        "proposed_claim_type": None,
        "evidence_role": None,
        "materialised": False,
        "new_claim_type_introduced": False,
        "preconditions": {
            "explicit_intervention_in_source": True,
            "explicit_intervention_in_graph_record": False,
            "biomarker_specific_result": False,
            "differential_treatment_effect_for_biomarker": False,
            "population_defined": True,
            "outcome_defined": True,
            "locator_sufficient_for_claim": False,
        },
        "unmet_preconditions": [
            "explicit_intervention_in_graph_record",
            "biomarker_specific_result",
            "differential_treatment_effect_for_biomarker",
            "locator_sufficient_for_claim",
        ],
        "why_not": (
            "La fonte nomina cetuximab, ma il record del grafo non porta alcun "
            "intervento: costruirvi sopra una proposizione terapeutica significherebbe "
            "aggiungere l'intervento, cioe' inventarlo. E anche se l'intervento ci "
            "fosse, l'abstract non riporta un risultato separato per L858R — la "
            "variante compare una sola volta, in una frase sulla composizione della "
            "popolazione, e per di piu' congiunta con exon 19 deletion. La "
            "conclusione sullo stato mutazionale e' per di piu' di *assenza* di "
            "modificazione dell'effetto."
        ),
        "forbidden_transformations_avoided": [
            "trattamento_dello_studio_to_intervento_del_claim_senza_locator",
            "analisi_di_sottogruppo_to_effetto_individuale_su_L858R",
            "composizione_della_popolazione_to_risultato_sul_biomarcatore",
            "interazione_non_significativa_to_beneficio",
            "prognostic_to_predictive_automatico",
            "predictive_design_to_predictive_claim_specifico",
            "cetuximab_citato_to_supporto_terapeutico_per_L858R",
        ],
        "decisions": list(record["decisions"]),
        "reopen_when": (
            "Il full text di PMID:24662454 diventa disponibile e riporta un esito "
            "separato per L858R, oppure il record del grafo acquisisce un intervento "
            "documentato."
        ),
    }


# --- parte B ------------------------------------------------------------------


def _source_unit_review(review: Mapping[str, Any]) -> dict[str, Any]:
    unit = review["pmid_24122810_source_unit"]
    access = next(
        a for a in review["source_access"] if a["source_id"] == "PMID:24122810"
    )
    operational = next(
        u
        for u in load_jsonl(CORPUS / "active_source_profile_units.jsonl")
        if u["profile_unit_id"] == unit["source_unit_id"]
    )
    return {
        "review_version": REVIEW_VERSION,
        "source_unit_id": unit["source_unit_id"],
        "source_id": "PMID:24122810",
        "unit_type": unit["unit_type"],
        "population": unit["population"],
        "disease": unit["disease"],
        "sample_scope": unit["sample_scope"],
        "assay_or_method": unit["assay_or_method"],
        "biomarkers": list(unit["biomarkers"]),
        "findings": [dict(f) for f in unit["findings"]],
        "limitations": [dict(x) for x in unit["limitations"]],
        "locator": dict(unit["locator"]),
        "access_type": unit["access_type"],
        "source_access_status": access["source_access_status"],
        "material_sha256": access["abstract_sha256"],
        "first_reviewer": unit["first_reviewer"],
        "review_status": unit["review_status"],
        "review_independence": unit["review_independence"],
        "propagation_policy": unit["propagation_policy"],
        "hard_filterable": unit["hard_filterable"],
        "final_evaluable": unit["final_evaluable"],
        "evaluability_reason": unit["evaluability_reason"],
        "requires_second_independent_review": unit["requires_second_independent_review"],
        "operational_unit_state_before": {
            "review_status": operational["review_status"],
            "is_evaluable": operational["is_evaluable"],
            "source_spans": len(operational["source_spans"]),
        },
        "operational_unit_modified": False,
        "operational_unit_modification_note": (
            "La revisione e' registrata qui e non nel corpus: promuovere lo stato "
            "della unit operativa richiederebbe la seconda revisione indipendente, "
            "che non e' avvenuta."
        ),
        "gold_used": False,
    }


def _locator_audit(
    review: Mapping[str, Any], claim_reviews: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Ogni decisione con il locator piu' preciso disponibile. Il PMID non basta."""
    rows: list[dict[str, Any]] = []

    for key, question in sorted(review["evidence_347"]["questions"].items()):
        locator = question.get("locator")
        rows.append(
            {
                "locator_id": f"LOC-evidence-347-{key}",
                "scope_id": "evidence:347",
                "decision_element": key,
                "source_id": "PMID:24662454",
                "locator_kind": "abstract_sentence" if locator else "none",
                "section": (locator or {}).get("section"),
                "abstract_sentence": (locator or {}).get("abstract_sentence"),
                "page": None,
                "table": None,
                "figure": None,
                "supplement": None,
                "arm": None,
                "subgroup": None,
                "verbatim_present": bool(question.get("verbatim")),
                "locator_status": "sufficient" if locator else "insufficient",
                "pmid_only": False,
            }
        )

    unit = review["pmid_24122810_source_unit"]
    for index, finding in enumerate(unit["findings"]):
        rows.append(
            {
                "locator_id": f"LOC-PU-24122810-finding-{index}",
                "scope_id": unit["source_unit_id"],
                "decision_element": f"finding_{index}",
                "source_id": "PMID:24122810",
                "locator_kind": "abstract_sentence",
                "section": finding["locator"]["section"],
                "abstract_sentence": finding["locator"]["abstract_sentence"],
                "page": None,
                "table": None,
                "figure": None,
                "supplement": None,
                "arm": None,
                "subgroup": None,
                "verbatim_present": True,
                "locator_status": "sufficient",
                "pmid_only": False,
            }
        )

    for claim_review in claim_reviews:
        for index, item in enumerate(claim_review["supported_content"]):
            rows.append(
                {
                    "locator_id": f"LOC-{claim_review['review_id']}-support-{index}",
                    "scope_id": claim_review["graph_evidence_id"],
                    "decision_element": f"supported_content_{index}",
                    "source_id": "PMID:24122810",
                    "locator_kind": "abstract_sentence",
                    "section": item["locator"]["section"],
                    "abstract_sentence": item["locator"]["abstract_sentence"],
                    "page": None,
                    "table": None,
                    "figure": None,
                    "supplement": None,
                    "arm": None,
                    "subgroup": None,
                    "verbatim_present": True,
                    "locator_status": "sufficient",
                    "pmid_only": False,
                }
            )
        for index, item in enumerate(claim_review["required_narrowing"]):
            rows.append(
                {
                    "locator_id": f"LOC-{claim_review['review_id']}-narrowing-{index}",
                    "scope_id": claim_review["graph_evidence_id"],
                    "decision_element": f"required_narrowing_{item['field']}",
                    "source_id": "PMID:24122810",
                    "locator_kind": "abstract_sentence",
                    "section": item["locator"]["section"],
                    "abstract_sentence": item["locator"]["abstract_sentence"],
                    "page": None,
                    "table": None,
                    "figure": None,
                    "supplement": None,
                    "arm": None,
                    "subgroup": None,
                    "verbatim_present": True,
                    "locator_status": "sufficient",
                    "pmid_only": False,
                }
            )
    return rows


def _limitations(
    review: Mapping[str, Any], claim_reviews: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unit = review["pmid_24122810_source_unit"]
    for item in unit["limitations"]:
        rows.append(
            {
                "scope_id": unit["source_unit_id"],
                "scope_kind": "source_unit",
                "source_id": "PMID:24122810",
                "code": item["code"],
                "detail": item["detail"],
                "blocks_final": item["code"]
                in ("ABSTRACT_ONLY_NO_FULL_TEXT", "PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC"),
            }
        )
    for claim_review in claim_reviews:
        for code in claim_review["limitation_codes"]:
            rows.append(
                {
                    "scope_id": claim_review["graph_evidence_id"],
                    "scope_kind": "diagnostic_claim",
                    "source_id": "PMID:24122810",
                    "code": code,
                    "detail": f"Limitazione ereditata dalla source unit e conservata sul claim {claim_review['claim_id']}.",
                    "blocks_final": code == "ABSTRACT_ONLY_NO_FULL_TEXT",
                }
            )
    for code in review["evidence_347"]["reason_codes"]:
        rows.append(
            {
                "scope_id": "evidence:347",
                "scope_kind": "graph_evidence_record",
                "source_id": "PMID:24662454",
                "code": code,
                "detail": "Ragione registrata dalla revisione documentale di evidence:347.",
                "blocks_final": True,
            }
        )
    return rows


# --- packet ciechi ------------------------------------------------------------


def _blind(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Rimuove ogni traccia della decisione del primo reviewer."""
    return {k: v for k, v in payload.items() if k not in BLINDED_FIELDS}


def _second_review_packets(
    review: Mapping[str, Any], claim_reviews: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Packet per la seconda revisione: materiale, non conclusioni.

    Portano la fonte, i locator e le domande. Non portano il verdetto del primo
    reviewer, ne' i suoi reason code, ne' una raccomandazione: un packet che
    suggerisce la risposta non produce una revisione indipendente, produce una
    conferma.
    """
    cache = {
        row["pmid"]: row
        for row in load_jsonl(CURATION / "source_abstract_cache.jsonl")
    }
    packets: dict[str, dict[str, Any]] = {}

    abstract_347 = cache["24662454"]
    packets["SR-evidence-347.json"] = {
        "packet_id": "SR-evidence-347",
        "packet_version": REVIEW_VERSION,
        "blind": True,
        "first_reviewer_decision_included": False,
        "recommendation_included": False,
        "graph_evidence_id": "evidence:347",
        "source_id": "PMID:24662454",
        "source_title": abstract_347["title"],
        "source_access_status": "full_text_unavailable",
        "material_provided": "abstract",
        "material_sha256": abstract_347["abstract_sha256"],
        "abstract_sections": [
            {"label": s["label"], "text": s["text"]}
            for s in abstract_347["abstract_sections"]
        ],
        "graph_assertion": {
            "direction": review["evidence_347"]["graph_direction"],
            "biomarker": review["evidence_347"]["graph_biomarker"],
            "disease": review["evidence_347"]["graph_disease"],
            "intervention": review["evidence_347"]["graph_intervention"],
        },
        "questions_to_answer": [
            "Quale trattamento viene studiato?",
            "L'intervento e' esplicito nella fonte? E nel record del grafo?",
            "Quale popolazione e' analizzata?",
            "Quale biomarcatore o gruppo mutazionale e' valutato?",
            "L858R ha un risultato separato?",
            "Exon 19 deletion ha un risultato separato?",
            "Il risultato riguarda prognosi indipendente dal trattamento, interazione biomarcatore-trattamento, risposta, overall survival, progression-free survival o altro?",
            "Lo studio consente un'interpretazione predittiva?",
            "Il risultato e' statisticamente separabile per L858R?",
            "Il record del grafo e' correggibile senza modificare biomarcatore, intervento o popolazione?",
        ],
        "allowed_decisions": [
            "therapeutic_predictive_claim_proposal_supported",
            "predictive_scope_unresolved",
            "graph_prognostic_direction_rejected",
            "insufficient_source_access",
        ],
        "instructions": (
            "Rispondere dalle sole frasi dell'abstract fornito, indicando per ogni "
            "risposta sezione e indice di frase. Non usare conoscenza generale, non "
            "usare il titolo come prova, non ricostruire contenuto assente."
        ),
    }

    for claim_review in sorted(claim_reviews, key=lambda r: r["graph_evidence_id"]):
        abstract = cache["24122810"]
        blinded_unit = _blind(review["pmid_24122810_source_unit"])
        packets[f"SR-{claim_review['graph_evidence_id'].replace(':', '-')}.json"] = {
            "packet_id": f"SR-{claim_review['graph_evidence_id'].replace(':', '-')}",
            "packet_version": REVIEW_VERSION,
            "blind": True,
            "first_reviewer_decision_included": False,
            "recommendation_included": False,
            "graph_evidence_id": claim_review["graph_evidence_id"],
            "claim_id": claim_review["claim_id"],
            "claim_type": "diagnostic_claim",
            "biomarker": claim_review["biomarker"],
            "asserted_disease_scope": claim_review["current_disease_scope"],
            "asserted_interpretation": claim_review["current_interpretation"],
            "source_id": "PMID:24122810",
            "source_title": abstract["title"],
            "source_access_status": "full_text_unavailable",
            "material_provided": "abstract",
            "material_sha256": abstract["abstract_sha256"],
            "abstract_sections": [
                {"label": s["label"], "text": s["text"]}
                for s in abstract["abstract_sections"]
            ],
            "source_unit_context": {
                k: blinded_unit[k]
                for k in ("source_unit_id", "unit_type", "population", "sample_scope", "assay_or_method")
                if k in blinded_unit
            },
            "questions_to_answer": [
                "La fusione specifica e' identificata testualmente nella fonte?",
                "Quale popolazione e' studiata e con quale numerosita'?",
                "Quale disease scope e' realmente misurato?",
                "Qual e' la frequenza riportata delle fusioni FGFR2?",
                "La prevalenza e' separabile per singolo partner di fusione?",
                "Quale confronto con altri tumori e' riportato?",
                "E' riportata mutua esclusivita' con KRAS/BRAF?",
                "Che cosa significa 'molecular subtype' in questa fonte?",
                "E' affermata un'utilita' diagnostica esplicita?",
                "E' affermata un'associazione terapeutica, e con quale disegno?",
                "Qual e' il locator piu' preciso disponibile per ciascuna risposta?",
            ],
            "allowed_decisions": [
                "diagnostic_claim_confirmed",
                "diagnostic_claim_partial",
                "diagnostic_claim_requires_narrowing",
                "diagnostic_claim_rejected",
                "insufficient_source_support",
            ],
            "instructions": (
                "Valutare questo claim da solo, senza confrontarlo con l'altra fusione. "
                "Rispondere dalle sole frasi dell'abstract, indicando sezione e indice "
                "di frase. Non attribuire al singolo partner dati riportati in forma "
                "aggregata. Non dedurre utilita' clinica."
            ),
        }
    return packets


# --- simulazione --------------------------------------------------------------


def _shadow_simulation(
    review: Mapping[str, Any], claim_reviews: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Cosa cambierebbe nel repository 1.1. Non applicata."""
    claims = load_jsonl(SHADOW_V11 / "evidence_claims_v1_1.jsonl")
    therapeutic = [c for c in claims if c["claim_domain"] == "therapeutic"]
    diagnostic = [c for c in claims if c["claim_domain"] == "diagnostic"]

    confirmed = [r for r in claim_reviews if r["decision"] == "diagnostic_claim_confirmed"]
    narrowing = [
        r for r in claim_reviews if r["decision"] == "diagnostic_claim_requires_narrowing"
    ]
    rejected = [r for r in claim_reviews if r["decision"] == "diagnostic_claim_rejected"]

    # Restringere il disease scope cambia un campo che entra nell'identita' del
    # claim: gli ID andranno ricalcolati, e i vecchi ritirati invece che
    # modificati in place.
    identity_affected = [
        r
        for r in narrowing
        if any(n["field"] in ("disease_scope", "biomarker") for n in r["required_narrowing"])
    ]

    return {
        "review_version": REVIEW_VERSION,
        "applied": False,
        "shadow_repository_modified": False,
        "current_state": {
            "evidence_claims_total": len(claims),
            "therapeutic_claims": len(therapeutic),
            "diagnostic_claims": len(diagnostic),
            "prognostic_claims": 0,
            "parents_without_claims": 3,
        },
        "evidence_347": {
            "outcome": "remains_parent_without_claim",
            "claim_proposal": None,
            "legacy_statement_status": "promotion_blocked_pending_full_text",
            "legacy_statement_status_changes": False,
            "full_text_blocker_retained": True,
            "graph_prognostic_direction": "rejected",
            "note": (
                "La direzione prognostica e' rifiutata sulla base dell'abstract, ma il "
                "record non acquisisce alcun claim: il rifiuto chiude una domanda e non "
                "ne apre un'altra."
            ),
        },
        "diagnostic_claims": {
            "confirmed": len(confirmed),
            "requires_narrowing": len(narrowing),
            "partial": 0,
            "rejected": len(rejected),
            "insufficient": 0,
            "identity_affected_by_narrowing": len(identity_affected),
            "details": [
                {
                    "graph_evidence_id": r["graph_evidence_id"],
                    "claim_id": r["claim_id"],
                    "decision": r["decision"],
                    "narrowing": [
                        {
                            "field": n["field"],
                            "current": n["current"],
                            "narrowed_to": n["narrowed_to"],
                        }
                        for n in r["required_narrowing"]
                    ],
                    "claim_id_would_change": any(
                        n["field"] in ("disease_scope", "biomarker")
                        for n in r["required_narrowing"]
                    ),
                }
                for r in sorted(claim_reviews, key=lambda x: x["graph_evidence_id"])
            ],
        },
        "derived_counts": {
            "claims_confirmed_as_is": len(confirmed),
            "claims_to_modify": len(narrowing),
            "claims_to_retire": len(rejected) + len(identity_affected),
            "claims_to_create_after_narrowing": len(identity_affected),
            "evidence_claims_total_after": len(claims),
            "total_unchanged_reason": (
                "Il restringimento non cambia il numero di claim: ogni claim ristretto "
                "sostituisce se stesso con un ID nuovo. Il totale resta quello che e'."
            ),
        },
        "link_impact": {
            "links_to_retire": len(identity_affected),
            "links_to_create": len(identity_affected),
            "links_unchanged": len(diagnostic) - len(identity_affected),
            "executed": False,
        },
        "view_impact": {
            "views_to_regenerate": len(identity_affected),
            "views_to_retire": 0,
            "executed": False,
        },
        "repository_1_1_readiness_after_review": {
            "shadow_repository_revision_ready": True,
            "revision_required": len(narrowing) > 0,
            "corpus_promotion_ready": False,
            "reason": (
                "I due claim diagnostici richiedono un restringimento del disease scope "
                "prima di poter essere considerati stabili, e la seconda revisione "
                "indipendente non e' avvenuta."
            ),
        },
    }


def _manifest(
    artifacts: Mapping[str, str],
    review: Mapping[str, Any],
    claim_reviews: Sequence[Mapping[str, Any]],
    simulation: Mapping[str, Any],
) -> dict[str, Any]:
    operational = {
        relative: sha256_text((REPO_ROOT / relative).read_text(encoding="utf-8"))
        for relative in OPERATIONAL_ARTIFACTS
    }
    return {
        "review_version": REVIEW_VERSION,
        "reviewer_role": review["reviewer_role"],
        "review_independence": review["review_independence"],
        "review_date": review["review_date"],
        "sources_reviewed": 2,
        "full_text_acquired": 0,
        "full_text_unavailable": 2,
        "secondary_sources_used": False,
        "content_reconstructed": False,
        "evidence_347": {
            "decisions": list(review["evidence_347"]["decisions"]),
            "claim_created": False,
            "intervention_invented": False,
            "legacy_statement_status": review["evidence_347"]["legacy_statement_status"],
        },
        "diagnostic_claims": {
            r["graph_evidence_id"]: r["decision"]
            for r in sorted(claim_reviews, key=lambda x: x["graph_evidence_id"])
        },
        "source_unit_review_status": review["pmid_24122810_source_unit"]["review_status"],
        "second_review_packets": sorted(
            name.split("/")[1] for name in artifacts if name.startswith("second_review_packets/")
        ),
        "second_review_packets_blind": True,
        "simulation_applied": False,
        "invariants": {
            "operational_corpus_modified": False,
            "operational_adapter_modified": False,
            "operational_retriever_modified": False,
            "operational_scoring_modified": False,
            "shadow_repository_1_0_modified": False,
            "shadow_repository_1_1_modified": False,
            "disease_hierarchy_modified": False,
            "new_claim_types_introduced": False,
            "terminology_mappings_promoted": False,
            "gold_used": False,
            "corpus_promoted": False,
        },
        "operational_artifact_sha256": operational,
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
    }


def write(output: Path, artifacts: Mapping[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(artifacts.items()):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-input-order", action="store_true")
    parser.add_argument("--check-determinism", action="store_true")
    args = parser.parse_args()

    artifacts = build(reverse=args.reverse_input_order)
    if args.check_determinism:
        other = build(reverse=not args.reverse_input_order)
        if artifacts != other:
            differing = sorted(k for k in artifacts if artifacts[k] != other.get(k))
            raise SystemExit(f"output non deterministico: {differing}")
        print("determinismo verificato: output identico con ordine invertito")
    write(args.output, artifacts)
    print(f"scritti {len(artifacts)} artefatti in {args.output}")


if __name__ == "__main__":
    main()
