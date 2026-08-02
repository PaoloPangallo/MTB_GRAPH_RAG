"""Read-only registry assembled exclusively from checked-in local assets."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .models import OntologyConcept


def _norm(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[â€â€‘â€’â€“â€”]", "-", value)
    value = re.sub(r"\s+", " ", value)
    return value


class OntologyRegistry:
    def __init__(self) -> None:
        self.concepts: dict[str, OntologyConcept] = {}
        self._lookup: dict[tuple[str, str], str] = {}
        self.relations: list[dict[str, str]] = []
        self.asset_records: list[dict[str, str]] = []

    @classmethod
    def from_local_assets(cls, repo_root: Path) -> "OntologyRegistry":
        registry = cls()
        registry._load_disease_assets(repo_root)
        registry._load_drug_alias_asset(repo_root)
        registry._load_explicit_intervention_asset(repo_root)
        registry._load_diagnostic_asset(repo_root)
        return registry

    def add_concept(self, concept: OntologyConcept) -> None:
        existing = self.concepts.get(concept.registry_key)
        if existing:
            existing.synonyms = sorted(set(existing.synonyms + concept.synonyms))
            existing.parents = sorted(set(existing.parents + concept.parents))
            existing.children = sorted(set(existing.children + concept.children))
            existing.relation_kinds.update(concept.relation_kinds)
            return
        self.concepts[concept.registry_key] = concept
        self._index(concept)

    def _index(self, concept: OntologyConcept) -> None:
        for value in [concept.label, *concept.synonyms]:
            self._lookup[(concept.entity_type, _norm(value))] = concept.registry_key

    def add_relation(self, parent_key: str, child_key: str, source: str, version: str | None) -> None:
        parent = self.concepts.get(parent_key)
        child = self.concepts.get(child_key)
        if not parent or not child:
            return
        if child_key not in parent.children:
            parent.children.append(child_key)
        if parent_key not in child.parents:
            child.parents.append(parent_key)
        child.relation_kinds[parent_key] = "is_a"
        self.relations.append(
            {
                "parent": parent_key,
                "child": child_key,
                "relation": "is_a",
                "source": source,
                "version": version or "",
            }
        )

    def resolve(self, entity_type: str, value: str | None) -> OntologyConcept | None:
        if not value:
            return None
        key = self._lookup.get((entity_type, _norm(value)))
        return self.concepts.get(key) if key else None

    def concept(self, key: str | None) -> OntologyConcept | None:
        return self.concepts.get(key) if key else None

    def descendant_path(self, ancestor_key: str, descendant_key: str) -> list[str] | None:
        if ancestor_key == descendant_key:
            return [ancestor_key]
        queue: list[tuple[str, list[str]]] = [(ancestor_key, [ancestor_key])]
        seen = {ancestor_key}
        while queue:
            current, path = queue.pop(0)
            for child in self.concepts[current].children:
                if child in seen:
                    continue
                next_path = path + [child]
                if child == descendant_key:
                    return next_path
                seen.add(child)
                queue.append((child, next_path))
        return None

    def _load_disease_assets(self, root: Path) -> None:
        snapshot_rel = Path("benchmarks/mtb_evidence/v3/disease_hierarchy_policy/verified_alias_registry_snapshot.json")
        relation_rel = Path("benchmarks/mtb_evidence/v3/disease_hierarchy_policy/explicit_hierarchy_relations.jsonl")
        snapshot = json.loads((root / snapshot_rel).read_text(encoding="utf-8"))
        source = snapshot.get("alias_source", str(snapshot_rel))
        version = snapshot.get("alias_version")
        for group in snapshot.get("groups", []):
            key = f"disease:{group['canonical_key']}"
            self.add_concept(
                OntologyConcept(
                    registry_key=key,
                    canonical_id=None,
                    label=group["canonical_key"],
                    entity_type="disease",
                    synonyms=group.get("members", []),
                    source=source,
                    version=version,
                )
            )
            self.asset_records.append(
                {"asset_type": "disease_alias_group", "registry_key": key, "source": source, "version": version or ""}
            )
        for raw in (root / relation_rel).read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if not row.get("child_canonical_key") or not row.get("parent_canonical_key"):
                continue
            child_key = f"disease:{row['child_canonical_key']}"
            parent_key = f"disease:{row['parent_canonical_key']}"
            if child_key not in self.concepts:
                self.add_concept(
                    OntologyConcept(
                        registry_key=child_key,
                        canonical_id=None,
                        label=row["child_canonical_key"],
                        entity_type="disease",
                        synonyms=[row["child_term"]],
                        source=row["relation_source"],
                        version=row["relation_source_version"],
                    )
                )
            if parent_key not in self.concepts:
                self.add_concept(
                    OntologyConcept(
                        registry_key=parent_key,
                        canonical_id=None,
                        label=row["parent_canonical_key"],
                        entity_type="disease",
                        synonyms=[row["parent_term"]],
                        source=row["relation_source"],
                        version=row["relation_source_version"],
                    )
                )
            self.add_relation(parent_key, child_key, row["relation_source"], row["relation_source_version"])

    def _load_drug_alias_asset(self, root: Path) -> None:
        alias_rel = Path("benchmarks/mtb_evidence/pilot/audit_lib/aliases.py")
        text = (root / alias_rel).read_text(encoding="utf-8")
        block = re.search(r"DRUG_ALIASES: dict\[str, str\] = \{(.*?)\n\}", text, re.S)
        if not block:
            return
        pairs = re.findall(r"\s*['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]", block.group(1))
        source = "benchmarks/mtb_evidence/pilot/audit_lib/aliases.py::DRUG_ALIASES"
        version = "verified-local-drug-aliases/1.0"
        for alias, canonical in pairs:
            key = f"intervention:{_norm(canonical)}"
            if key not in self.concepts:
                self.add_concept(OntologyConcept(key, None, canonical, "intervention", [], [], [], source, version))
            self.concepts[key].synonyms.append(alias)
            self._lookup[("intervention", _norm(alias))] = key
            self.asset_records.append({"asset_type": "intervention_alias", "registry_key": key, "source": source, "version": version})

    def _load_explicit_intervention_asset(self, root: Path) -> None:
        rel = Path("benchmarks/mtb_evidence/v3/terminology_mapping_closure/canonicalization_contract.json")
        path = root / rel
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        source = str(rel)
        for row in data.get("mappings", data.get("mapping_table", [])):
            if not isinstance(row, dict):
                continue
            source_literal = row.get("source_literal") or row.get("source")
            canonical = row.get("canonical_label") or row.get("canonical")
            canonical_id = row.get("canonical_id")
            if not source_literal or not canonical:
                continue
            key = f"intervention:{_norm(canonical)}"
            if key not in self.concepts:
                self.add_concept(OntologyConcept(key, canonical_id, canonical, "intervention", [], [], [], source, "local-contract"))
            if str(row.get("eligible_for_exact_match", "false")).lower() == "true":
                self.concepts[key].synonyms.append(source_literal)
                self._lookup[("intervention", _norm(source_literal))] = key
            self.asset_records.append({"asset_type": "intervention_mapping", "registry_key": key, "source": source, "version": "local-contract"})

    def _load_diagnostic_asset(self, root: Path) -> None:
        rel = Path("benchmarks/mtb_evidence/v3/non_therapeutic_source_closure/diagnostic_claim_reviews.jsonl")
        path = root / rel
        if not path.exists():
            return
        source = str(rel)
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            label = row.get("biomarker") or row.get("diagnostic_subject")
            if not label:
                continue
            key = f"diagnostic:{_norm(label)}"
            self.add_concept(OntologyConcept(key, None, label, "diagnostic", [], [], [], source, "local-diagnostic-review/1.0"))
            self.asset_records.append({"asset_type": "diagnostic_record", "registry_key": key, "source": source, "version": "local-diagnostic-review/1.0"})

    def iter_concepts(self) -> Iterable[OntologyConcept]:
        return self.concepts.values()
