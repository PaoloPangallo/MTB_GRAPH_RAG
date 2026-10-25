"""Offline materialization. Source bytes are verified before interpretation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from .models import SourceRef, Term
from .registry import Registry, IDENTITY_SCOPES
from .surface import lookup_key, molecular_surface


def checked_bytes(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Source hash mismatch: {path.name}")
    return data


def import_snapshot(path: Path) -> tuple[list[Term], list[dict]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "terminology-source/1.0":
        raise ValueError("Unsupported snapshot schema")
    filename = manifest["file"]
    if Path(filename).name != filename:
        raise ValueError("Snapshot must be local")
    data = checked_bytes(path.parent / filename, manifest["sha256"])
    terms, mappings = [], []
    if manifest["format"] != "OBO":
        raise ValueError("Unsupported snapshot format; provide a reviewed OBO export")
    for block in data.decode("utf-8").split("[Term]")[1:]:
        # Stop before another stanza; typedefs are not concepts.
        block = block.split("[Typedef]")[0]
        rows = defaultdict(list)
        for line in block.splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                rows[key].append(value)
        if not rows["id"] or not rows["name"]:
            continue
        cid = rows["id"][0]
        source = SourceRef(filename, manifest["version"], manifest["sha256"], cid)
        for key, predicate in (("xref", "XREF_UNSPECIFIED"), ("is_a", "IS_A"), ("replaced_by", "REPLACED_BY")):
            mappings.extend({"subject": cid, "object": value.split()[0], "predicate": predicate,
                             "source": source.__dict__} for value in rows[key])
        if "true" in rows["is_obsolete"]:
            mappings.append({"subject": cid, "object": cid, "predicate": "OBSOLETE", "source": source.__dict__})
            continue
        terms.append(Term(manifest["domain"], cid, rows["name"][0], "PREFERRED", source))
        for value in rows["synonym"]:
            match = re.match(r'^"((?:[^"\\]|\\.)*)" (EXACT|BROAD|NARROW|RELATED)\b', value)
            if match:
                terms.append(Term(manifest["domain"], cid, match[1].replace('\\"', '"'), match[2], source))
        # OBO alt_id is an identifier alias, not a cross-resource xref.
        terms.extend(Term(manifest["domain"], cid, value, "EXACT", source) for value in rows["alt_id"])
    return terms, mappings


def _write(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def reconcile_source_identifiers(source_terms: list[Term], authority_terms: list[Term],
                                 authority_mappings: list[dict] | None = None) -> tuple[list[Term], list[dict]]:
    """Repair lost DOID zero padding only against a unique pinned authority.

    Numeric similarity alone never establishes identity: an identity-scope label
    must also agree. Authoritative IDs, conflicting IDs and other namespaces
    remain untouched. Both source assertions are preserved in the audit mapping.
    """
    by_number: dict[int, list[Term]] = defaultdict(list)
    authoritative_ids = {t.concept_id for t in authority_terms}
    reserved_ids = set(authoritative_ids)
    reserved_ids.update(t.label for t in authority_terms if t.domain == "DISEASE"
                        and t.alias_scope == "EXACT" and re.fullmatch(r"DOID:[0-9]+", t.label))
    reserved_ids.update(m["subject"] for m in authority_mappings or []
                        if m.get("predicate") == "OBSOLETE")
    spellings: dict[int, set[str]] = defaultdict(set)
    for cid in reserved_ids:
        if re.fullmatch(r"DOID:[0-9]+", cid):
            spellings[int(cid[5:])].add(cid)
    for term in authority_terms:
        if term.domain == "DISEASE" and re.fullmatch(r"DOID:[0-9]+", term.concept_id):
            by_number[int(term.concept_id[5:])].append(term)
    result, mappings = [], []
    for term in source_terms:
        candidates = []
        if (term.domain == "DISEASE" and term.concept_id not in reserved_ids
                and re.fullmatch(r"DOID:[0-9]+", term.concept_id)):
            bucket = by_number.get(int(term.concept_id[5:]), [])
            if len(spellings.get(int(term.concept_id[5:]), set())) == 1:
                candidates = [t for t in bucket if t.alias_scope in IDENTITY_SCOPES
                              and term.alias_scope in IDENTITY_SCOPES
                              and lookup_key("DISEASE", t.label) == lookup_key("DISEASE", term.label)]
        if candidates:
            authority = candidates[0]
            result.append(replace(term, concept_id=authority.concept_id))
            mappings.append({"subject": term.concept_id, "object": authority.concept_id,
                             "predicate": "SOURCE_IDENTIFIER_RECONCILIATION",
                             "source": term.source.__dict__, "authority_source": authority.source.__dict__,
                             "rule": "UNIQUE_DOID_NUMERIC_ID_AND_EXACT_LABEL"})
        else:
            result.append(term)
    return result, mappings


def build_registry(source_root: Path, gca_path: Path, approved_snapshots: list[Path],
                   output_root: Path, expected_hashes: dict[str, str], *, gca_hash: str) -> dict:
    tables = {}
    for filename, digest in sorted(expected_hashes.items()):
        data = checked_bytes(source_root / filename, digest)
        tables[filename] = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    corpus = checked_bytes(gca_path, gca_hash)
    terms, mappings, entities = [], [], {}
    version = "terminology/1.2"

    def add(domain, cid, label, filename, locator, scope="PREFERRED", gene_id=None, reference=None):
        if label:
            terms.append(Term(domain, cid, label, scope,
                              SourceRef(filename, "KB/GCA4-source", expected_hashes[filename], str(locator)),
                              gene_id, reference))

    genes = {}
    for row in tables["node_gene.csv"]:
        cid = "NCBIGene:" + row["entrez_id"]
        genes[cid] = row["hugo_symbol"]
        add("GENE", cid, row["hugo_symbol"], "node_gene.csv", row["entrez_id"])
        for alias in row["aliases"].split(";"):
            add("GENE", cid, alias.strip(), "node_gene.csv", row["entrez_id"], "EXACT")
    variant_genes = defaultdict(set)
    for row in tables["edge_has_variant.csv"]:
        variant_genes[row["target_variant_id"]].add("NCBIGene:" + row["source_entrez_id"])
    variants = {}
    for row in tables["node_variant.csv"]:
        cid = "CIViCVariant:" + row["variant_id"]
        variants[cid] = {"name": row["variant_name"], "gene_ids": sorted(variant_genes[row["variant_id"]]),
                         "allele_registry_id": row["allele_registry_id"], "hgvs": row["hgvs_descriptions"].split(";")}
        entities[cid] = variants[cid]
        for gene in variants[cid]["gene_ids"] or [None]:
            add("VARIANT", cid, row["variant_name"], "node_variant.csv", row["variant_id"], gene_id=gene)
            for alias in variants[cid]["hgvs"]:
                add("VARIANT", cid, alias.strip(), "node_variant.csv", row["variant_id"], "EXACT", gene,
                    molecular_surface(alias).get("reference"))
    components = defaultdict(set)
    for row in tables["edge_in_molecular_profile.csv"]:
        components[row["target_molecular_profile_id"]].add("CIViCVariant:" + row["source_variant_id"])
    for row in tables["node_molecular_profile.csv"]:
        cid = "CIViCProfile:" + row["molecular_profile_id"]
        entities[cid] = {"name": row["name"], "variant_ids": sorted(components[row["molecular_profile_id"]])}
        add("PROFILE", cid, row["name"], "node_molecular_profile.csv", row["molecular_profile_id"])
        for alias in row["aliases"].split(";"):
            add("PROFILE", cid, alias.strip(), "node_molecular_profile.csv", row["molecular_profile_id"], "EXACT")
    for row in tables["node_evidence.csv"]:
        label = row["disease"]
        cid = "DOID:" + row["doid"].removeprefix("DOID:") if row["doid"] else "LOCAL:Disease:" + hashlib.sha256(label.casefold().encode()).hexdigest()[:16]
        add("DISEASE", cid, label, "node_evidence.csv", row["evidence_id"])
    for row in tables["node_drug.csv"]:
        cid = row["concept_id"]
        if not cid:
            continue
        add("INTERVENTION", cid, row["drug_name"], "node_drug.csv", cid)
        add("INTERVENTION", cid, row["drug_claim_name"], "node_drug.csv", cid, "EXACT")
    for row in tables["nodes_clinical_trials.csv"]:
        add("TRIAL", row["nct_id"], row["title"], "nodes_clinical_trials.csv", row["nct_id"])
        entities[row["nct_id"]] = {"conditions": [x.strip() for x in row["conditions"].split("|") if x.strip()]}
    snapshots, authority_terms = [], []
    for path in approved_snapshots:
        imported, mapped = import_snapshot(path)
        authority_terms.extend(imported)
        mappings.extend(mapped)
        snapshots.append(json.loads(path.read_text(encoding="utf-8")))
    # Never repair a source identifier explicitly retired by the authority.
    obsolete = {m["subject"] for m in mappings if m["predicate"] == "OBSOLETE"}
    active_source = [t for t in terms if t.concept_id not in obsolete]
    reconciled, repairs = reconcile_source_identifiers(active_source, authority_terms, mappings)
    terms = reconciled + [t for t in terms if t.concept_id in obsolete] + authority_terms
    mappings.extend(repairs)
    retired = [t for t in terms if t.concept_id in obsolete]
    # Preserve historical source assertions for audit, never reinstate an
    # ontology-retired identifier or silently follow its replacement.
    entities["_retired_source_terms"] = {"terms": [t.__dict__ | {"source": t.source.__dict__} for t in retired]}
    registry = Registry([t for t in terms if t.concept_id not in obsolete], version, mappings, entities)
    conflicts = []
    for (domain, key), values in sorted(registry._lookup.items()):
        ids = sorted({t.concept_id for t in values if t.alias_scope in IDENTITY_SCOPES})
        if len(ids) > 1:
            conflicts.append({"domain": domain, "key": key, "concept_ids": ids})
    overlay = {}
    for line in corpus.decode("utf-8").splitlines():
        row = json.loads(line)
        profile = (row.get("source_properties") or {}).get("profile") or {}
        pid = str(profile.get("molecular_profile_id") or (row.get("subject") or {}).get("id") or "")
        pid = "CIViCProfile:" + pid.removeprefix("CIViCProfile:")
        if pid in entities:
            overlay[row["candidate_id"]] = {"profile_id": pid, **entities[pid],
                "components": [{"variant_id": vid, **variants[vid]} for vid in entities[pid]["variant_ids"] if vid in variants]}
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "terminology-manifest/1.0", "registry_version": version,
                "builder_version": "terminology-builder/1.2", "registry_file": "registry.json",
                "registry_sha256": _write(output_root / "registry.json", registry.to_dict()),
                "overlay_file": "gca_overlay.json", "overlay_sha256": _write(output_root / "gca_overlay.json", {"gca_sha256": gca_hash, "candidates": overlay}),
                "gca_sha256": gca_hash, "source_hashes": expected_hashes, "snapshots": snapshots,
                "conflict_count": len(conflicts), "term_count": len(registry.terms),
                "conflicts_sha256": _write(output_root / "conflicts.json", {"conflicts": conflicts})}
    _write(output_root / "manifest.json", manifest)
    return manifest
