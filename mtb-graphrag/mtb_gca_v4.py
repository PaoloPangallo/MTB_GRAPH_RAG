"""Deterministic GCA 4.0 materialization from the current CleanGraphData export.

The module deliberately does not import or read the v2/v3 repositories while
constructing candidates.  Structural graph edges are attached as lineage;
only the declared semantic units enter the eligible denominator.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

MATERIALIZER_VERSION = "gca-materializer/4.0"
REPOSITORY_VERSION = "graph_candidate_repository/4.0"
PMID_RE = re.compile(r"^[0-9]+$")
NCT_RE = re.compile(r"^NCT[0-9]{8}$", re.IGNORECASE)

NODE_FILES = {
    "node_gene.csv": ("Gene", "entrez_id"),
    "node_variant.csv": ("Variant", "variant_id"),
    "node_molecular_profile.csv": ("MolecularProfile", "molecular_profile_id"),
    "node_evidence.csv": ("Evidence", "evidence_id"),
    "node_drug.csv": ("Drug", "concept_id"),
    "node_companion_diagnostic.csv": ("CompanionDiagnostic", "device_id"),
    "nodes_clinical_trials.csv": ("Trial", "nct_id"),
}

STRUCTURAL_FILES = {"edge_has_variant.csv", "edge_in_molecular_profile.csv"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_id(dataset: str, row_number: int, row: dict[str, str]) -> str:
    return f"row:{dataset}:{row_number}:{_hash(row)[:16]}"


def _node_id(node_type: str, identifier: str) -> str:
    return f"{node_type}:{identifier}"


def _read_tables(source_root: Path) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    for path in sorted(source_root.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            tables[path.name] = list(csv.DictReader(handle))
    return tables


class CleanGraphData:
    """Immutable-in-practice view over the current CSV export."""

    def __init__(self, source_root: Path):
        self.source_root = source_root.resolve()
        self.tables = _read_tables(self.source_root)
        self.nodes: dict[str, dict[str, dict[str, str]]] = {}
        self.node_types: dict[str, str] = {}
        for filename, (node_type, key) in NODE_FILES.items():
            rows = self.tables.get(filename, [])
            self.node_types[filename] = node_type
            self.nodes[filename] = {_clean(row.get(key)): row for row in rows if _clean(row.get(key))}

    def node(self, filename: str, identifier: str) -> dict[str, str] | None:
        return self.nodes.get(filename, {}).get(_clean(identifier))

    def row_ids(self, filename: str) -> list[str]:
        return [_row_id(filename, number, row) for number, row in enumerate(self.tables.get(filename, []), 2)]

    def source_hash(self) -> str:
        return _hash({name: _file_hash(self.source_root / name) for name in sorted(self.tables)})

    def inventory(self) -> dict[str, Any]:
        return {
            "source_root": str(self.source_root),
            "files": {name: len(rows) for name, rows in sorted(self.tables.items())},
            "nodes": {
                name: {
                    "node_type": NODE_FILES[name][0],
                    "records": len(self.tables.get(name, [])),
                    "unique_ids": len(self.nodes.get(name, {})),
                    "duplicate_ids": len(self.tables.get(name, [])) - len(self.nodes.get(name, {})),
                }
                for name in sorted(NODE_FILES)
            },
        }


def _documents(evidence: dict[str, str], document_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw = _clean(evidence.get("citation_id"))
    if not raw:
        return []
    item: dict[str, Any] = {"pmid": raw, "scope": "evidence_record"}
    if raw in document_map and document_map[raw].get("pmcid"):
        item["pmcid"] = document_map[raw]["pmcid"]
    if not PMID_RE.fullmatch(raw):
        item["valid_pmid"] = False
    return [item]


def _load_document_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    result: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                result[_clean(row.get("pmid"))] = row
    return result


def _unit(family: str, unit_id: str, source_dataset: str, row_number: int, row: dict[str, str]) -> dict[str, Any]:
    return {
        "relation_family": family,
        "unit_id": unit_id,
        "source_datasets": [source_dataset],
        "source_record_ids": [_row_id(source_dataset, row_number, row)],
        "source_rows": {source_dataset: row},
        "row_number": row_number,
    }


def enumerate_semantic_units(graph: CleanGraphData) -> list[dict[str, Any]]:
    """Enumerate only autonomous semantic units, not structural edges."""
    units: list[dict[str, Any]] = []
    declarations = [
        ("EVIDENCE_STATEMENT", "edge_has_evidence.csv"),
        ("EVIDENCE_DRUG", "edge_targets_drug.csv"),
        ("GENE_DRUG", "edge_interacts_with.csv"),
        ("TRIAL_DRUG", "edges_trial_drug.csv"),
        ("TRIAL_GENE", "edges_trial_gene.csv"),
        ("DRUG_COMPANION_DIAGNOSTIC", "edge_has_companion_diagnostic.csv"),
        ("COMPANION_DIAGNOSTIC_GENE", "edge_diagnoses_gene.csv"),
    ]
    for family, dataset in declarations:
        for number, row in enumerate(graph.tables.get(dataset, []), 2):
            key_fields = {
                "EVIDENCE_STATEMENT": (row.get("source_molecular_profile_id"), row.get("target_evidence_id")),
                "EVIDENCE_DRUG": (row.get("source_evidence_id"), row.get("target_drug_concept_id")),
                "GENE_DRUG": (row.get("source_gene_entrez_id"), row.get("target_drug_concept_id")),
                "TRIAL_DRUG": (row.get("nct_id"), row.get("drug_name_normalized") or row.get("drug_name_raw")),
                "TRIAL_GENE": (row.get("nct_id"), row.get("gene_symbol")),
                "DRUG_COMPANION_DIAGNOSTIC": (row.get("source_drug_concept_id"), row.get("target_device_id")),
                "COMPANION_DIAGNOSTIC_GENE": (row.get("source_device_id"), row.get("target_gene_entrez_id")),
            }[family]
            units.append(_unit(family, f"{family}:{number}:{_hash(key_fields)[:16]}", dataset, number, row))
    return units


def _lookup_edge_ids(graph: CleanGraphData, dataset: str, predicate) -> list[str]:
    return [_row_id(dataset, n, row) for n, row in enumerate(graph.tables.get(dataset, []), 2) if predicate(row)]


def _evidence_context(graph: CleanGraphData, evidence_id: str) -> tuple[list[str], list[str], list[str]]:
    profile_edges = []
    profiles = []
    variants = []
    for n, row in enumerate(graph.tables.get("edge_has_evidence.csv", []), 2):
        if _clean(row.get("target_evidence_id")) == evidence_id:
            profile_id = _clean(row.get("source_molecular_profile_id"))
            profile_edges.append(_row_id("edge_has_evidence.csv", n, row))
            profiles.append(profile_id)
            for vn, variant_row in enumerate(graph.tables.get("edge_in_molecular_profile.csv", []), 2):
                if _clean(variant_row.get("target_molecular_profile_id")) == profile_id:
                    variants.append(_node_id("Variant", _clean(variant_row.get("source_variant_id"))))
    return profile_edges, profiles, variants


def _excluded(unit: dict[str, Any], reason: str, detail: str = "") -> dict[str, Any]:
    return {
        "unit_id": unit["unit_id"],
        "relation_family": unit["relation_family"],
        "reason": reason,
        "detail": detail,
        "source_datasets": unit["source_datasets"],
        "source_record_ids": unit["source_record_ids"],
        "source_rows": unit["source_rows"],
    }


def _candidate(
    family: str, unit: dict[str, Any], subject: dict[str, Any], predicate: str,
    object_node: dict[str, Any], graph_path: list[str], node_ids: list[str], edge_ids: dict[str, list[str]],
    documents: list[dict[str, Any]], context: dict[str, Any], source_properties: dict[str, Any],
) -> dict[str, Any]:
    if family == "EVIDENCE_STATEMENT":
        semantic_key = "|".join([family, object_node["id"]])
    elif family == "EVIDENCE_DRUG":
        semantic_key = "|".join([family, subject["id"], object_node["id"]])
    else:
        semantic_key = "|".join([family, subject["id"], object_node["id"]])
    identity = f"{semantic_key}|{unit['unit_id']}"
    return {
        "candidate_id": f"GCA4-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}",
        "relation_family": family,
        "relation_origin": "DIRECT",
        "subject": subject,
        "predicate": predicate,
        "object": object_node,
        "context": context,
        "semantic_key": semantic_key,
        "source_record_ids": unit["source_record_ids"],
        "source_datasets": unit["source_datasets"],
        "source_properties": source_properties,
        "graph_path": graph_path,
        "node_ids": node_ids,
        "edge_ids_by_dataset": edge_ids,
        "document_identifiers": documents,
        "materialization_rule": f"gca/4.0/{family.lower()}",
        "materializer_version": MATERIALIZER_VERSION,
    }


def _build_candidate(graph: CleanGraphData, unit: dict[str, Any], document_map: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    family = unit["relation_family"]
    row = next(iter(unit["source_rows"].values()))
    source = unit["source_datasets"][0]
    common = {"context": {}, "source_properties": {source: row}}
    if family == "EVIDENCE_STATEMENT":
        profile_id = _clean(row.get("source_molecular_profile_id")); evidence_id = _clean(row.get("target_evidence_id"))
        evidence = graph.node("node_evidence.csv", evidence_id); profile = graph.node("node_molecular_profile.csv", profile_id)
        if not profile or not evidence: return None, _excluded(unit, "INVALID_REFERENCE", "missing profile or evidence node")
        if not _clean(evidence.get("evidence_statement")): return None, _excluded(unit, "MISSING_REQUIRED_FIELD", "empty evidence_statement")
        profile_edges, _, variants = _evidence_context(graph, evidence_id)
        docs = _documents(evidence, document_map)
        context = {"disease": _clean(evidence.get("disease")), "doid": _clean(evidence.get("doid")), "evidence_type": _clean(evidence.get("evidence_type"))}
        node_ids = [_node_id("MolecularProfile", profile_id), *variants, _node_id("Evidence", evidence_id)]
        edges = {"edge_has_evidence.csv": unit["source_record_ids"], "edge_in_molecular_profile.csv": []}
        edges["edge_has_evidence.csv"] = profile_edges or unit["source_record_ids"]
        edges["edge_in_molecular_profile.csv"] = _lookup_edge_ids(graph, "edge_in_molecular_profile.csv", lambda r: _clean(r.get("target_molecular_profile_id")) == profile_id)
        return _candidate(family, unit, {"id": _node_id("MolecularProfile", profile_id), "label": _clean(profile.get("name")), "type": "MolecularProfile"}, "has_evidence_statement", {"id": _node_id("Evidence", evidence_id), "label": _clean(evidence.get("evidence_statement")), "type": "Evidence"}, node_ids, node_ids, edges, docs, context, {"evidence": evidence, "profile": profile}), None
    if family == "EVIDENCE_DRUG":
        evidence_id = _clean(row.get("source_evidence_id")); drug_id = _clean(row.get("target_drug_concept_id"))
        evidence = graph.node("node_evidence.csv", evidence_id); drug = graph.node("node_drug.csv", drug_id)
        if not evidence or not drug: return None, _excluded(unit, "INVALID_REFERENCE", "missing evidence or drug node")
        profile_edges, profiles, variants = _evidence_context(graph, evidence_id)
        docs = _documents(evidence, document_map)
        context = {"disease": _clean(evidence.get("disease")), "doid": _clean(evidence.get("doid")), "evidence_type": _clean(evidence.get("evidence_type")), "evidence_level": _clean(row.get("evidence_level"))}
        nodes = [_node_id("Evidence", evidence_id), *[_node_id("MolecularProfile", p) for p in profiles], *variants, _node_id("Drug", drug_id)]
        edges = {"edge_targets_drug.csv": unit["source_record_ids"], "edge_has_evidence.csv": profile_edges, "edge_in_molecular_profile.csv": _lookup_edge_ids(graph, "edge_in_molecular_profile.csv", lambda r: _clean(r.get("target_molecular_profile_id")) in set(profiles))}
        return _candidate(family, unit, {"id": _node_id("Evidence", evidence_id), "label": _clean(evidence.get("evidence_statement")), "type": "Evidence"}, "targets_drug", {"id": _node_id("Drug", drug_id), "label": _clean(drug.get("drug_name") or drug.get("drug_claim_name")), "type": "Drug"}, nodes, nodes, edges, docs, context, {"evidence": evidence, "drug": drug, "edge": row}), None
    if family == "GENE_DRUG":
        gene_id = _clean(row.get("source_gene_entrez_id")); drug_id = _clean(row.get("target_drug_concept_id"))
        gene = graph.node("node_gene.csv", gene_id); drug = graph.node("node_drug.csv", drug_id)
        if not gene or not drug: return None, _excluded(unit, "INVALID_REFERENCE", "missing gene or drug node")
        nodes = [_node_id("Gene", gene_id), _node_id("Drug", drug_id)]
        return _candidate(family, unit, {"id": nodes[0], "label": _clean(gene.get("hugo_symbol")), "type": "Gene"}, "interacts_with", {"id": nodes[1], "label": _clean(drug.get("drug_name") or drug.get("drug_claim_name")), "type": "Drug"}, nodes, nodes, {source: unit["source_record_ids"]}, [], {}, {"edge": row, "gene": gene, "drug": drug}), None
    if family == "TRIAL_DRUG":
        nct = _clean(row.get("nct_id")); trial = graph.node("nodes_clinical_trials.csv", nct); name = _clean(row.get("drug_name_normalized") or row.get("drug_name_raw"))
        if not trial or not NCT_RE.fullmatch(nct): return None, _excluded(unit, "INVALID_REFERENCE", "missing or malformed NCT")
        if not name: return None, _excluded(unit, "MISSING_REQUIRED_FIELD", "empty trial drug name")
        nodes = [_node_id("Trial", nct), f"DrugName:{name}"]
        return _candidate(family, unit, {"id": nodes[0], "label": _clean(trial.get("title")), "type": "Trial"}, "has_trial_intervention", {"id": nodes[1], "label": name, "type": "DrugName"}, nodes, nodes, {source: unit["source_record_ids"]}, [{"nct": nct}], {}, {"trial": trial, "edge": row}), None
    if family == "TRIAL_GENE":
        nct = _clean(row.get("nct_id")); trial = graph.node("nodes_clinical_trials.csv", nct); gene = _clean(row.get("gene_symbol"))
        if not trial or not NCT_RE.fullmatch(nct): return None, _excluded(unit, "INVALID_REFERENCE", "missing or malformed NCT")
        if not gene: return None, _excluded(unit, "MISSING_REQUIRED_FIELD", "empty trial gene")
        nodes = [_node_id("Trial", nct), f"GeneSymbol:{gene.upper()}"]
        return _candidate(family, unit, {"id": nodes[0], "label": _clean(trial.get("title")), "type": "Trial"}, "has_trial_gene", {"id": nodes[1], "label": gene.upper(), "type": "GeneSymbol"}, nodes, nodes, {source: unit["source_record_ids"]}, [{"nct": nct}], {}, {"trial": trial, "edge": row}), None
    if family == "DRUG_COMPANION_DIAGNOSTIC":
        drug_id = _clean(row.get("source_drug_concept_id")); device_id = _clean(row.get("target_device_id")); drug = graph.node("node_drug.csv", drug_id); device = graph.node("node_companion_diagnostic.csv", device_id)
        if not drug or not device: return None, _excluded(unit, "INVALID_REFERENCE", "missing drug or companion diagnostic node")
        nodes = [_node_id("Drug", drug_id), _node_id("CompanionDiagnostic", device_id)]
        return _candidate(family, unit, {"id": nodes[0], "label": _clean(drug.get("drug_name") or drug.get("drug_claim_name")), "type": "Drug"}, "has_companion_diagnostic", {"id": nodes[1], "label": _clean(device.get("device_name")), "type": "CompanionDiagnostic"}, nodes, nodes, {source: unit["source_record_ids"]}, [], {}, {"drug": drug, "device": device, "edge": row}), None
    if family == "COMPANION_DIAGNOSTIC_GENE":
        device_id = _clean(row.get("source_device_id")); gene_id = _clean(row.get("target_gene_entrez_id")); device = graph.node("node_companion_diagnostic.csv", device_id); gene = graph.node("node_gene.csv", gene_id)
        if not device or not gene: return None, _excluded(unit, "INVALID_REFERENCE", "missing companion diagnostic or gene node")
        nodes = [_node_id("CompanionDiagnostic", device_id), _node_id("Gene", gene_id)]
        return _candidate(family, unit, {"id": nodes[0], "label": _clean(device.get("device_name")), "type": "CompanionDiagnostic"}, "diagnoses_gene", {"id": nodes[1], "label": _clean(gene.get("hugo_symbol")), "type": "Gene"}, nodes, nodes, {source: unit["source_record_ids"]}, [], {}, {"device": device, "gene": gene, "edge": row}), None
    return None, _excluded(unit, "UNSUPPORTED_RELATION_TYPE", family)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return _file_hash(path)


def _v2_semantic_key(row: dict[str, Any]) -> str:
    raw_rule = _clean(row.get("materialization_rule_id"))
    rule = raw_rule.replace("gca/2.0/", "").replace("evidence-to-drug", "EVIDENCE_DRUG").replace("evidence-statement", "EVIDENCE_STATEMENT").replace("gene-drug-interaction", "GENE_DRUG").replace("trial-drug", "TRIAL_DRUG").replace("trial-gene", "TRIAL_GENE").replace("companion-diagnostic", "COMPANION_DIAGNOSTIC_GENE")
    subject = _clean((row.get("subject") or {}).get("id")); predicate = _clean(row.get("predicate")); obj = _clean((row.get("object") or {}).get("id"))
    evidence_ids = row.get("evidence_record_ids") or []
    if rule == "EVIDENCE_STATEMENT" and evidence_ids:
        return "|".join([rule, f"Evidence:{_clean(evidence_ids[0]).split(':')[-1]}"])
    if rule == "EVIDENCE_DRUG" and evidence_ids:
        return "|".join([rule, f"Evidence:{_clean(evidence_ids[0]).split(':')[-1]}", obj])
    if rule == "COMPANION_DIAGNOSTIC_GENE":
        return "|".join([rule, obj, subject])
    if rule == "TRIAL_DRUG":
        subject = subject.replace("ClinicalTrial:", "Trial:")
        obj = obj.replace("Drug:", "DrugName:")
        return "|".join([rule, subject, obj])
    if rule == "TRIAL_GENE":
        subject = subject.replace("ClinicalTrial:", "Trial:")
        obj = obj.replace("Gene:", "GeneSymbol:")
        return "|".join([rule, subject, obj])
    return "|".join([rule, subject, obj])


def _semantic_diff(candidates: list[dict[str, Any]], v2_path: Path | None) -> dict[str, Any]:
    if not v2_path or not v2_path.is_file():
        return {"status": "V2_NOT_AVAILABLE"}
    v2_keys = Counter(_v2_semantic_key(json.loads(line)) for line in v2_path.open(encoding="utf-8") if line.strip())
    v4_keys = Counter(row["semantic_key"] for row in candidates)
    common = sum((v2_keys & v4_keys).values())
    families = sorted({key.split("|", 1)[0] for key in v2_keys} | {key.split("|", 1)[0] for key in v4_keys})
    by_family = {}
    for family in families:
        old = Counter({key: value for key, value in v2_keys.items() if key.startswith(family + "|")})
        new = Counter({key: value for key, value in v4_keys.items() if key.startswith(family + "|")})
        by_family[family] = {"v2": sum(old.values()), "v4": sum(new.values()), "semantic_common": sum((old & new).values()), "v2_only": sum((old - new).values()), "v4_only": sum((new - old).values())}
    return {"status": "COMPARED", "v2_candidates": sum(v2_keys.values()), "v4_candidates": len(candidates), "semantic_common": common, "v2_only": sum((v2_keys - v4_keys).values()), "v4_only": sum((v4_keys - v2_keys).values()), "v2_duplicate_semantic_keys": sum(v2_keys.values()) - len(v2_keys), "v4_duplicate_semantic_keys": sum(v4_keys.values()) - len(v4_keys), "by_family": by_family}


def _sample_audit(candidates: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    special: dict[str, dict[str, Any]] = {}
    for row in sorted(candidates, key=lambda item: item["candidate_id"]):
        family_key = f"family:{row['relation_family']}"
        if len(selected[family_key]) < 10:
            selected[family_key].append(row)
        if row["document_identifiers"] and "with_pmid" not in special and any(item.get("pmid") for item in row["document_identifiers"]):
            special["with_pmid"] = row
        if row["document_identifiers"] and "with_nct" not in special and any(item.get("nct") for item in row["document_identifiers"]):
            special["with_nct"] = row
        if not row["document_identifiers"] and "only_kg" not in special:
            special["only_kg"] = row
    rows = []
    for category, samples in sorted(selected.items()):
        rows.extend({"sample_category": category, "sample_index": index, "candidate_id": row["candidate_id"], "relation_family": row["relation_family"], "traceability_check": "PASS" if row["source_record_ids"] and row["source_datasets"] and row["graph_path"] else "FAIL", "source_datasets": row["source_datasets"], "source_record_ids": row["source_record_ids"], "graph_path": row["graph_path"], "node_ids": row["node_ids"], "edge_ids_by_dataset": row["edge_ids_by_dataset"], "document_identifiers": row["document_identifiers"]} for index, row in enumerate(samples, 1))
    rows.extend({"sample_category": category, "sample_index": 1, "candidate_id": row["candidate_id"], "relation_family": row["relation_family"], "traceability_check": "PASS" if row["source_record_ids"] and row["source_datasets"] and row["graph_path"] else "FAIL", "source_datasets": row["source_datasets"], "source_record_ids": row["source_record_ids"], "graph_path": row["graph_path"], "node_ids": row["node_ids"], "edge_ids_by_dataset": row["edge_ids_by_dataset"], "document_identifiers": row["document_identifiers"]} for category, row in sorted(special.items()))
    rows.extend({"sample_category": "excluded", "sample_index": index, **row, "traceability_check": "PASS" if row["source_record_ids"] else "FAIL"} for index, row in enumerate(exclusions[:10], 1))
    return rows


def materialize_source(source_root: Path, output_root: Path, *, document_manifest: Path | None = None, v2_path: Path | None = None) -> dict[str, Any]:
    graph = CleanGraphData(source_root)
    output_root.mkdir(parents=True, exist_ok=True)
    units = enumerate_semantic_units(graph)
    document_map = _load_document_map(document_manifest)
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for unit in units:
        candidate, exclusion = _build_candidate(graph, unit, document_map)
        if candidate is not None: candidates.append(candidate)
        if exclusion is not None: exclusions.append(exclusion)
    candidates.sort(key=lambda row: row["candidate_id"])
    exclusions.sort(key=lambda row: row["unit_id"])
    candidate_hash = _write_jsonl(output_root / "candidates.jsonl", candidates)
    exclusion_hash = _write_jsonl(output_root / "exclusions.jsonl", exclusions)
    family_input = Counter(unit["relation_family"] for unit in units)
    family_materialized = Counter(row["relation_family"] for row in candidates)
    family_excluded = Counter(row["relation_family"] for row in exclusions)
    coverage = {family: {"eligible": family_input[family], "materialized": family_materialized[family], "excluded": family_excluded[family], "coverage_percent": round(100 * family_materialized[family] / family_input[family], 6) if family_input[family] else 0.0} for family in sorted(family_input)}
    source_distribution = Counter(dataset for row in candidates for dataset in row["source_datasets"])
    candidate_pmids = {item.get("pmid") for row in candidates for item in row["document_identifiers"] if item.get("pmid")}
    candidate_pmcids = {item.get("pmcid") for row in candidates for item in row["document_identifiers"] if item.get("pmcid")}
    candidate_ncts = {item.get("nct") for row in candidates for item in row["document_identifiers"] if item.get("nct")}
    document_statuses = {pmid: _clean(value.get("final_document_status")) for pmid, value in document_map.items()}
    document_coverage = {
        "candidates_with_pmid": sum(bool(row["document_identifiers"]) and any(item.get("pmid") for item in row["document_identifiers"]) for row in candidates),
        "pmid_distinct": len(candidate_pmids),
        "pmcid_distinct": len(candidate_pmcids),
        "candidates_with_nct": sum(any(item.get("nct") for item in row["document_identifiers"]) for row in candidates),
        "nct_distinct": len(candidate_ncts),
        "full_text_pmc_pmids": len({pmid for pmid in candidate_pmids if document_statuses.get(pmid) == "FULL_TEXT_PMC"}),
        "abstract_only_pmids": len({pmid for pmid in candidate_pmids if document_statuses.get(pmid) == "ABSTRACT_ONLY"}),
        "unavailable_pmids": len({pmid for pmid in candidate_pmids if document_statuses.get(pmid) in {"DOCUMENT_UNAVAILABLE", "TERMINAL_RESOLUTION_FAILURE"}}),
        "candidates_only_kg": sum(not row["document_identifiers"] and not any(item.get("nct") for item in row["document_identifiers"]) for row in candidates),
        "manifest_used": str(document_manifest) if document_manifest else None,
    }
    validation = {
        "duplicate_candidate_ids": len(candidates) - len({row["candidate_id"] for row in candidates}),
        "duplicate_semantic_units": len(units) - len({unit["unit_id"] for unit in units}),
        "missing_subject_or_object": sum(not row.get("subject") or not row.get("object") for row in candidates),
        "invalid_pmid": sum(any(item.get("valid_pmid") is False for item in row["document_identifiers"]) for row in candidates),
        "invalid_nct": sum(any(item.get("nct") and not NCT_RE.fullmatch(item["nct"]) for item in row["document_identifiers"]) for row in candidates),
        "source_traceability_incomplete": sum(not row["source_record_ids"] or not row["source_datasets"] for row in candidates),
        "invalid_references_unreported": 0,
        "structural_edges_excluded_from_eligible_denominator": sorted(STRUCTURAL_FILES),
        "trial_eligibility_treated_as_context": True,
        "derived_companion_composite_materialized": False,
    }
    summary = {"eligible_semantic_units": len(units), "materialized_candidates": len(candidates), "excluded_with_reason": len(exclusions), "unaccounted_eligible_units": len(units) - len(candidates) - len(exclusions), "families": coverage}
    summary["document_coverage"] = document_coverage
    manifest = {"repository_version": REPOSITORY_VERSION, "materializer_version": MATERIALIZER_VERSION, "source_root": str(graph.source_root), "source_hash": graph.source_hash(), "candidates_sha256": candidate_hash, "exclusions_sha256": exclusion_hash, "summary": summary, "validation": validation, "runtime_repository_still_v2": True, "evaluation_units_executed": 0}
    files = {"candidates": "candidates.jsonl", "exclusions": "exclusions.jsonl", "manifest": "manifest.json", "coverage": "coverage_report.json", "semantic_diff": "semantic_diff_v2_v4.json", "source_distribution": "source_distribution.json", "validation": "validation_report.json", "determinism": "determinism_report.json", "sample_audit": "sample_audit.jsonl"}
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_root / "coverage_report.json").write_text(json.dumps({"coverage": coverage, "summary": summary}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_root / "semantic_diff_v2_v4.json").write_text(json.dumps(_semantic_diff(candidates, v2_path), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_distribution_report = {name: {"candidate_count": count, "percent": round(100 * count / len(candidates), 6) if candidates else 0.0} for name, count in sorted(source_distribution.items())}
    (output_root / "source_distribution.json").write_text(json.dumps(source_distribution_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_root / "validation_report.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_jsonl(output_root / "sample_audit.jsonl", _sample_audit(candidates, exclusions))
    determinism = {"materializer_version": MATERIALIZER_VERSION, "candidates_sha256": candidate_hash, "exclusions_sha256": exclusion_hash, "sorted_candidate_ids": True, "sorted_exclusion_ids": True}
    (output_root / "determinism_report.json").write_text(json.dumps(determinism, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"candidates": candidates, "exclusions": exclusions, "summary": summary, "hashes": {"candidates_sha256": candidate_hash, "exclusions_sha256": exclusion_hash}, "manifest": manifest, "files": files}
