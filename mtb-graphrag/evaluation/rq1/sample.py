"""Campione stratificato di GraphCandidateAssertion per la revisione umana (§6).

Il campione è **deterministico**: a parità di corpus produce le stesse 50 righe.
Le colonne del revisore restano vuote — nessun giudizio umano viene precompilato,
e nessun output di modello viene scritto in quelle colonne.

Le etichette di strato sono ausili di campionamento, non giudizi clinici. In
particolare ``disease_specificity`` usa una lista esplicita di termini generici
di sede/istologia: serve solo a garantire che il campione contenga sia malattie
specifiche sia contenitori ampi, e non viene usata in nessuna metrica.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Any, Callable, Iterable

#: Termini che denotano un contenitore diagnostico ampio piuttosto che una
#: malattia specifica. Usati solo per stratificare.
GENERIC_DISEASE_TERMS = (
    "cancer", "carcinoma", "neoplasm", "solid tumor", "solid tumour",
    "advanced solid tumor", "any cancer type", "tumor", "malignancy", "neoplasia",
)

SAMPLE_SIZE = 50


def _labels(entities: Iterable[dict[str, Any]] | None, kind: str | None = None) -> list[str]:
    out = []
    for entity in entities or []:
        if kind and entity.get("type") != kind:
            continue
        label = entity.get("label")
        if label:
            out.append(str(label))
    return out


def disease_specificity(candidate: dict[str, Any]) -> str:
    labels = [str(d.get("label") or "").lower() for d in candidate.get("disease") or []]
    if not labels:
        return "none"
    for label in labels:
        words = re.sub(r"[^a-z ]", " ", label).split()
        if len(words) > 1 and not any(term == label.strip() for term in GENERIC_DISEASE_TERMS):
            if not any(label.strip() == term for term in GENERIC_DISEASE_TERMS):
                return "specific"
    return "generic"


def pmids(candidate: dict[str, Any]) -> list[str]:
    return [
        str(i["pmid"]) for i in candidate.get("document_identifiers") or []
        if i.get("pmid")
    ]


def ncts(candidate: dict[str, Any]) -> list[str]:
    return [str(i["nct"]) for i in candidate.get("document_identifiers") or [] if i.get("nct")]


def _direction(candidate: dict[str, Any]) -> str:
    return str(candidate.get("direction") or "").lower()


#: Strati richiesti dal protocollo. Ordine significativo: il campionamento
#: assegna a ciascuno strato la prima candidate non ancora selezionata.
STRATA: "OrderedDict[str, Callable[[dict], bool]]" = OrderedDict([
    ("sensitivity", lambda c: "sensitivity" in _direction(c) or "response" in _direction(c)),
    ("resistance", lambda c: "resistance" in _direction(c)),
    ("therapeutic", lambda c: str(c.get("evidence_scope") or "").lower() == "predictive"),
    ("diagnostic", lambda c: str(c.get("evidence_scope") or "").lower() == "diagnostic"),
    ("prognostic", lambda c: str(c.get("evidence_scope") or "").lower() == "prognostic"),
    ("companion_diagnostic", lambda c: c.get("predicate") == "has_companion_diagnostic"),
    ("single_pmid", lambda c: len(set(pmids(c))) == 1),
    ("multi_pmid", lambda c: len(set(pmids(c))) > 1),
    ("with_nct", lambda c: bool(ncts(c))),
    ("no_identifier", lambda c: not (c.get("document_identifiers") or [])),
    ("specific_disease", lambda c: disease_specificity(c) == "specific"),
    ("generic_disease", lambda c: disease_specificity(c) == "generic"),
    ("specific_alteration", lambda c: bool(_labels(c.get("biomarkers"), "Variant"))),
    ("gene_only", lambda c: bool(_labels(c.get("biomarkers"), "Gene")) and not _labels(c.get("biomarkers"), "Variant")),
    ("gene_drug_interaction", lambda c: c.get("materialization_rule_id", "").endswith("gene-drug-interaction")),
    ("trial_association", lambda c: c.get("predicate") == "trial_association"),
    ("evidence_statement", lambda c: c.get("predicate") == "has_evidence_statement"),
])


def build_sample(
    candidates: list[dict[str, Any]],
    findings_by_candidate: dict[str, list[dict[str, Any]]],
    semantic_duplicate_ids: set[str],
    size: int = SAMPLE_SIZE,
) -> list[dict[str, Any]]:
    """Campione stratificato deterministico, con le colonne revisore vuote."""
    ordered = sorted(candidates, key=lambda c: c["candidate_id"])
    selected: "OrderedDict[str, tuple[dict, list[str]]]" = OrderedDict()

    def take(predicate, stratum: str, quota: int) -> None:
        taken = 0
        for candidate in ordered:
            if taken >= quota:
                return
            cid = candidate["candidate_id"]
            if cid in selected:
                continue
            if predicate(candidate):
                selected[cid] = (candidate, [stratum])
                taken += 1

    # Strati con difetto noto per primi: devono comparire nel campione.
    take(lambda c: any(f["class"] == "DIRECTION_INVERSION"
                       for f in findings_by_candidate.get(c["candidate_id"], [])),
         "graph_direction_inversion", 4)
    take(lambda c: any(f["class"] == "ALTERATION_LOST"
                       for f in findings_by_candidate.get(c["candidate_id"], [])),
         "graph_alteration_lost", 4)
    take(lambda c: c["candidate_id"] in semantic_duplicate_ids, "semantic_duplicate", 3)

    per_stratum = max(1, (size - len(selected)) // len(STRATA))
    for stratum, predicate in STRATA.items():
        take(predicate, stratum, per_stratum)
    for stratum, predicate in STRATA.items():
        if len(selected) >= size:
            break
        take(predicate, stratum, 1)

    rows = []
    for candidate, strata in list(selected.values())[:size]:
        cid = candidate["candidate_id"]
        findings = findings_by_candidate.get(cid, [])
        rows.append({
            "candidate_id": cid,
            "stratum": "|".join(strata),
            "materialization_rule_id": candidate.get("materialization_rule_id"),
            "predicate": candidate.get("predicate"),
            "subject": (candidate.get("subject") or {}).get("label"),
            "object": (candidate.get("object") or {}).get("label"),
            "disease": "|".join(_labels(candidate.get("disease"))),
            "gene": "|".join(_labels(candidate.get("biomarkers"), "Gene")),
            "alteration": "|".join(_labels(candidate.get("biomarkers"), "Variant")),
            "intervention": "|".join(_labels(candidate.get("interventions"))),
            "direction": candidate.get("direction"),
            "evidence_scope": candidate.get("evidence_scope"),
            "graph_path": "|".join(candidate.get("graph_path") or []),
            "parent_record": "|".join(candidate.get("evidence_record_ids") or []),
            "document_identifiers": "|".join(
                f"{k}:{i[k]}@{i.get('scope')}"
                for i in candidate.get("document_identifiers") or []
                for k in ("pmid", "nct", "doi") if i.get(k)
            ),
            "automatic_findings": "|".join(sorted({f["class"] for f in findings})) or "NONE",
            "automatic_findings_detail": json.dumps(findings, ensure_ascii=False)[:900] if findings else "",
            # Colonne del revisore: devono restare vuote.
            "reviewer_correct": "",
            "reviewer_complete": "",
            "reviewer_notes": "",
        })
    return rows


SAMPLE_FIELDS = [
    "candidate_id", "stratum", "materialization_rule_id", "predicate", "subject", "object",
    "disease", "gene", "alteration", "intervention", "direction", "evidence_scope",
    "graph_path", "parent_record", "document_identifiers",
    "automatic_findings", "automatic_findings_detail",
    "reviewer_correct", "reviewer_complete", "reviewer_notes",
]
