"""Confronto fra path eleggibili ricostruiti e GraphCandidateAssertion materializzate.

Il confronto è deterministico e su due livelli, che il report tiene separati
perché rispondono a due domande diverse:

**Contract fidelity**
    La candidate riproduce ciò che la regola dichiarata in
    ``materialization_rules.json`` prescrive? È una misura di correttezza
    dell'implementazione rispetto al proprio contratto.

**Graph fidelity**
    La candidate rappresenta fedelmente la relazione presente nel grafo? Una
    regola può essere implementata correttamente e nondimeno perdere
    informazione — per esempio conservando una sola variante di un profilo
    molecolare che ne contiene diverse. Questi casi sono difetti di
    rappresentazione anche quando la contract fidelity è perfetta, e vanno
    riportati come tali.

Nessuna delle due misura la validità clinica (livello D del protocollo).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from .canonical_key import canonical_key, norm_entity, norm_entity_set, norm_text
from .kg_source import EligiblePath, expected_payload, payload_identity

#: Classi di errore del protocollo (§4).
FIELD_MISMATCH = "FIELD_MISMATCH"
DIRECTION_INVERSION = "DIRECTION_INVERSION"
INTERVENTION_MISMATCH = "INTERVENTION_MISMATCH"
DISEASE_MISMATCH = "DISEASE_MISMATCH"
BIOMARKER_MISMATCH = "BIOMARKER_MISMATCH"
ALTERATION_LOST = "ALTERATION_LOST"
PATH_NOT_FOUND = "PATH_NOT_FOUND"
SOURCE_RECORD_MISMATCH = "SOURCE_RECORD_MISMATCH"
DOCUMENT_IDENTIFIER_MISMATCH = "DOCUMENT_IDENTIFIER_MISMATCH"
SPURIOUS_CANDIDATE = "SPURIOUS_CANDIDATE"
INCORRECT_DEDUPLICATION = "INCORRECT_DEDUPLICATION"
LINEAGE_BROKEN = "LINEAGE_BROKEN"
ORDER_MISMATCH = "ORDER_MISMATCH"
#: Regola di atomicità dichiarata ma non implementabile su questo export.
REGIMEN_SPLIT = "REGIMEN_SPLIT"

#: Campi confrontati uno a uno fra atteso e materializzato.
COMPARED_FIELDS = (
    "predicate", "subject", "object", "disease", "biomarkers", "interventions",
    "regimen", "direction", "evidence_scope", "diagnostic_scope", "graph_path",
    "node_ids", "edge_ids", "evidence_record_ids", "document_identifiers",
    "materialization_rule_id",
)

#: Direzioni che si escludono a vicenda: scambiarle inverte il significato clinico.
_OPPOSITE_DIRECTIONS = (
    ({"resistance", "resistance or non-response"}, {"sensitivity", "sensitivity/response", "response"}),
)


def load_candidates(path: str | Path) -> Iterator[dict[str, Any]]:
    """Stream dei record materializzati."""
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _field_equal(name: str, expected: Any, actual: Any) -> bool:
    """Uguaglianza per campo, con la normalizzazione documentata."""
    if name in {"subject", "object"}:
        return norm_entity(expected) == norm_entity(actual)
    if name in {"disease", "biomarkers", "interventions", "regimen"}:
        return norm_entity_set(expected) == norm_entity_set(actual)
    if name in {"direction", "evidence_scope", "diagnostic_scope"}:
        return norm_text(expected) == norm_text(actual)
    if name in {"graph_path", "node_ids"}:
        return list(expected or []) == list(actual or [])
    if name in {"edge_ids", "evidence_record_ids"}:
        return sorted(expected or []) == sorted(actual or [])
    if name == "document_identifiers":
        def key(rows):
            return sorted(
                (r.get("pmid") or r.get("nct") or r.get("doi") or "", r.get("scope") or "")
                for r in rows or []
            )
        return key(expected) == key(actual)
    return (expected or None) == (actual or None)


def _is_direction_inversion(expected: Any, actual: Any) -> bool:
    exp, act = norm_text(expected), norm_text(actual)
    if exp is None or act is None or exp == act:
        return False
    for left, right in _OPPOSITE_DIRECTIONS:
        if (exp in left and act in right) or (exp in right and act in left):
            return True
    return False


def _classify(name: str) -> str:
    return {
        "direction": FIELD_MISMATCH,
        "disease": DISEASE_MISMATCH,
        "biomarkers": BIOMARKER_MISMATCH,
        "interventions": INTERVENTION_MISMATCH,
        "evidence_record_ids": SOURCE_RECORD_MISMATCH,
        "document_identifiers": DOCUMENT_IDENTIFIER_MISMATCH,
        "node_ids": LINEAGE_BROKEN,
        "edge_ids": LINEAGE_BROKEN,
        "graph_path": LINEAGE_BROKEN,
    }.get(name, FIELD_MISMATCH)


@dataclass
class PathComparison:
    """Esito del confronto per un singolo path eleggibile."""

    path_id: str
    rule_id: str
    candidate_id: str | None
    matched: bool
    field_results: dict[str, bool] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    lineage_ok: bool | None = None
    graph_fidelity_findings: list[dict[str, Any]] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "rule_id": self.rule_id,
            "candidate_id": self.candidate_id,
            "matched": self.matched,
            "field_results": self.field_results,
            "findings": self.findings,
            "graph_fidelity_findings": self.graph_fidelity_findings,
            "lineage_ok": self.lineage_ok,
        }


class MaterializationComparator:
    """Accoppia path eleggibili e candidate, e classifica gli scostamenti."""

    def __init__(self, paths: Iterable[EligiblePath], candidates: Iterable[dict[str, Any]]):
        self.paths = list(paths)
        self.candidates = list(candidates)
        self._by_identity: dict[tuple, list[dict]] = defaultdict(list)
        for candidate in self.candidates:
            self._by_identity[self._candidate_identity(candidate)].append(candidate)

    @staticmethod
    def _candidate_identity(candidate: dict[str, Any]) -> tuple:
        return (
            candidate.get("materialization_rule_id"),
            candidate.get("predicate"),
            tuple(candidate.get("node_ids") or []),
            tuple(sorted(candidate.get("edge_ids") or [])),
        )

    def compare(self) -> dict[str, Any]:
        comparisons: list[PathComparison] = []
        consumed: set[int] = set()

        for path in self.paths:
            bucket = self._by_identity.get(path.identity, [])
            candidate = None
            for item in bucket:
                if id(item) not in consumed:
                    candidate = item
                    consumed.add(id(item))
                    break
            if candidate is None:
                comparisons.append(PathComparison(
                    path_id=path.path_id, rule_id=path.rule_id, candidate_id=None, matched=False,
                    findings=[{"class": PATH_NOT_FOUND, "detail": "nessuna candidate con questa identità di path"}],
                ))
                continue
            comparisons.append(self._compare_one(path, candidate))

        spurious = [c for c in self.candidates if id(c) not in consumed]
        return {
            "comparisons": comparisons,
            "spurious": spurious,
            "duplicates": self._duplicates(),
        }

    def _compare_one(self, path: EligiblePath, candidate: dict[str, Any]) -> PathComparison:
        result = PathComparison(
            path_id=path.path_id, rule_id=path.rule_id,
            candidate_id=candidate.get("candidate_id"), matched=True,
        )
        expected = dict(path.expected)
        expected["materialization_rule_id"] = path.rule_id

        for name in COMPARED_FIELDS:
            exp_value = expected.get(name)
            act_value = candidate.get(name)
            equal = _field_equal(name, exp_value, act_value)
            result.field_results[name] = equal
            if equal:
                continue
            finding = {
                "class": _classify(name),
                "field": name,
                "expected": exp_value if name not in {"source_properties"} else "<omesso>",
                "actual": act_value if name not in {"source_properties"} else "<omesso>",
            }
            if name == "direction" and _is_direction_inversion(exp_value, act_value):
                finding["class"] = DIRECTION_INVERSION
            result.findings.append(finding)

        # Lineage: candidate_id e payload_hash devono derivare dal payload emesso.
        expected_id, expected_hash = payload_identity(expected_payload(path, candidate.get("group_id")))
        actual_hash = candidate.get("payload_hash")
        recomputed_id, recomputed_hash = payload_identity({
            k: candidate.get(k) for k in (
                "subject", "predicate", "object", "disease", "biomarkers", "interventions",
                "regimen", "direction", "evidence_scope", "diagnostic_scope", "graph_path",
                "node_ids", "edge_ids", "evidence_record_ids", "document_identifiers",
                "source_properties", "materialization_rule_id", "group_id",
            )
        })
        self_consistent = (
            recomputed_hash == actual_hash and recomputed_id == candidate.get("candidate_id")
        )
        result.lineage_ok = self_consistent
        if not self_consistent:
            result.findings.append({
                "class": LINEAGE_BROKEN,
                "field": "payload_hash",
                "detail": "candidate_id/payload_hash non derivano dal payload serializzato",
            })
        result.field_results["payload_identity"] = bool(self_consistent)
        result.field_results["expected_payload_identity"] = bool(expected_hash == actual_hash)

        result.graph_fidelity_findings = self._graph_fidelity(path, candidate)
        return result

    @staticmethod
    def _graph_fidelity(path: EligiblePath, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        """Perdite di rappresentazione rispetto al grafo, indipendenti dal contratto."""
        out: list[dict[str, Any]] = []
        diag = path.diagnostics or {}
        dropped_variants = diag.get("dropped_variant_ids") or []
        if dropped_variants:
            out.append({
                "class": ALTERATION_LOST,
                "detail": "il profilo molecolare contiene più varianti; la candidate ne conserva una",
                "profile_variant_ids": diag.get("profile_variant_ids"),
                "selected_variant_id": diag.get("selected_variant_id"),
                "dropped_variant_ids": dropped_variants,
            })
        dropped_genes = diag.get("dropped_gene_ids") or []
        if dropped_genes:
            out.append({
                "class": BIOMARKER_MISMATCH,
                "detail": "la variante è collegata a più geni; la candidate ne conserva uno",
                "selected_gene_id": diag.get("selected_gene_id"),
                "dropped_gene_ids": dropped_genes,
            })
        # Direzione: per evidence-to-drug il predicato deriva da `significance`
        # e ignora `evidence_direction`. Un record che *non sostiene* una
        # resistenza produce comunque un predicato di resistenza.
        # Atomicità: `materialization_rules.json` dichiara che «inseparable
        # regimens remain units», ma il campo `regimen` non viene mai popolato e
        # un record Evidence con più farmaci produce candidate indipendenti, una
        # per farmaco. L'export non trasporta il tipo di interazione fra farmaci,
        # quindi la regola dichiarata non è implementabile su questa sorgente.
        if path.rule_id.endswith("evidence-to-drug") and (diag.get("evidence_drug_edge_count") or 0) > 1:
            out.append({
                "class": REGIMEN_SPLIT,
                "detail": (
                    "il record Evidence riguarda più farmaci; la candidate ne afferma uno solo "
                    "e il campo regimen resta vuoto"
                ),
                "evidence_drug_edge_count": diag.get("evidence_drug_edge_count"),
                "sibling_drug_names": diag.get("sibling_drug_names"),
                "regimen_emitted": candidate.get("regimen"),
                "drug_interaction_type_available": diag.get("drug_interaction_type_available"),
            })

        if path.rule_id.endswith("evidence-to-drug"):
            evidence_direction = (diag.get("evidence_direction") or "").strip().lower()
            predicate = candidate.get("predicate") or ""
            if evidence_direction and evidence_direction != "supports" and predicate.startswith("associated_with_"):
                out.append({
                    "class": DIRECTION_INVERSION,
                    "detail": (
                        "evidence_direction del record sorgente non è 'Supports' ma il predicato "
                        "afferma comunque l'associazione; la negazione resta solo in source_properties"
                    ),
                    "evidence_direction": diag.get("evidence_direction"),
                    "predicate": predicate,
                    "direction_field": candidate.get("direction"),
                })
        return out

    def _duplicates(self) -> dict[str, Any]:
        exact = Counter(c.get("payload_hash") for c in self.candidates)
        exact_groups = {h: n for h, n in exact.items() if n > 1}
        semantic = Counter(canonical_key(c).semantic() for c in self.candidates)
        semantic_groups = sum(1 for n in semantic.values() if n > 1)
        semantic_members = sum(n for n in semantic.values() if n > 1)
        id_counter = Counter(c.get("candidate_id") for c in self.candidates)
        return {
            "exact_duplicate_groups": len(exact_groups),
            "exact_duplicate_records": sum(exact_groups.values()),
            "semantic_duplicate_groups": semantic_groups,
            "semantic_duplicate_records": semantic_members,
            "repeated_candidate_ids": {i: n for i, n in id_counter.items() if n > 1},
        }


def aggregate(result: dict[str, Any], paths: list[EligiblePath], candidates_count: int) -> dict[str, Any]:
    """Metriche principali di RQ1."""
    comparisons: list[PathComparison] = result["comparisons"]
    matched = [c for c in comparisons if c.matched]
    missing = [c for c in comparisons if not c.matched]
    spurious = result["spurious"]

    field_totals: dict[str, dict[str, int]] = {}
    for name in COMPARED_FIELDS + ("payload_identity", "expected_payload_identity"):
        ok = sum(1 for c in matched if c.field_results.get(name) is True)
        field_totals[name] = {"ok": ok, "checked": len(matched)}

    finding_counts = Counter(f["class"] for c in matched for f in c.findings)
    graph_counts = Counter(f["class"] for c in matched for f in c.graph_fidelity_findings)

    by_rule: dict[str, dict[str, int]] = defaultdict(lambda: {"eligible": 0, "matched": 0, "missing": 0})
    for comparison in comparisons:
        bucket = by_rule[comparison.rule_id]
        bucket["eligible"] += 1
        bucket["matched" if comparison.matched else "missing"] += 1

    eligible = len(paths)
    precision = (candidates_count - len(spurious)) / candidates_count if candidates_count else None
    recall = len(matched) / eligible if eligible else None
    field_ok = sum(1 for c in matched if all(c.field_results.get(n) is True for n in COMPARED_FIELDS))

    doc_cov = Counter()
    for path in paths:
        ids = path.expected.get("document_identifiers") or []
        if any(i.get("pmid") for i in ids):
            doc_cov["with_pmid"] += 1
        if any(i.get("nct") for i in ids):
            doc_cov["with_nct"] += 1
        if not ids:
            doc_cov["without_identifier"] += 1

    return {
        "eligible_paths": eligible,
        "materialized_candidates": candidates_count,
        "matched_paths": len(matched),
        "missing_candidate_count": len(missing),
        "spurious_candidate_count": len(spurious),
        "materialization_precision": precision,
        "materialization_recall": recall,
        "field_completeness": (field_ok / len(matched)) if matched else None,
        "contract_field_fidelity_by_field": field_totals,
        "contract_finding_counts": dict(finding_counts),
        "graph_fidelity_finding_counts": dict(graph_counts),
        "direction_inversions_contract": finding_counts.get(DIRECTION_INVERSION, 0),
        "direction_inversions_graph": graph_counts.get(DIRECTION_INVERSION, 0),
        "coverage_by_rule": dict(by_rule),
        "coverage_by_document_identifier": dict(doc_cov),
        "duplicates": result["duplicates"],
        "exact_duplicate_rate": (
            result["duplicates"]["exact_duplicate_records"] / candidates_count if candidates_count else None
        ),
        "semantic_duplicate_rate": (
            result["duplicates"]["semantic_duplicate_records"] / candidates_count if candidates_count else None
        ),
    }
