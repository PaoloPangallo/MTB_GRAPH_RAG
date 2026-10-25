"""Read-only, deterministic trial context enrichment for retrieval.

The context is retrieval metadata only.  It is never evidence of efficacy,
eligibility, or therapeutic benefit and is kept separate from GCA semantics.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
from typing import Any


def normalize_nct(value: Any) -> str | None:
    text = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return text if re.fullmatch(r"NCT\d{8}", text) else None


def _default_root() -> Path:
    configured = os.getenv("RESEARCH_PIPELINE_TRIAL_CONTEXT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    # The canonical source export is kept at repository-level data_expl.
    # The older root-level duplicate is intentionally not used by default.
    return (Path(__file__).resolve().parents[4] / "data_expl" / "DatasetTESI" /
            "Dataset TESI" / "Clean_Graph_Data")


@dataclass(frozen=True)
class TrialContextRecord:
    nct_id: str
    genes: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    interventions_raw: tuple[str, ...] = ()
    interventions_normalized: tuple[str, ...] = ()
    provenance: dict[str, Any] | None = None


class TrialContextIndex:
    def __init__(self, records: dict[str, TrialContextRecord], provenance: dict[str, Any]):
        self._records = records
        self.provenance = provenance

    @classmethod
    def from_directory(cls, root: Path) -> "TrialContextIndex":
        root = Path(root)
        groups: dict[str, dict[str, list[str]]] = {}
        files = {
            "gene": root / "edges_trial_gene.csv",
            "drug": root / "edges_trial_drug.csv",
            "node": root / "nodes_clinical_trials.csv",
        }
        available_files = {k: p for k, p in files.items() if p.is_file()}
        source_files = {k: str(p) for k, p in available_files.items()}
        source_hashes = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in available_files.items()}
        for kind, path in files.items():
            if not path.is_file():
                continue
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    nct = normalize_nct(row.get("nct_id"))
                    if not nct:
                        continue
                    item = groups.setdefault(nct, {"genes": [], "conditions": [], "raw": [], "normalized": []})
                    if kind == "gene" and row.get("gene_symbol", "").strip():
                        item["genes"].append(row["gene_symbol"].strip())
                    elif kind == "drug":
                        raw = row.get("drug_name_raw", "").strip()
                        norm = row.get("drug_name_normalized", "").strip()
                        if raw:
                            item["raw"].append(raw)
                        if norm:
                            item["normalized"].append(norm)
                    elif kind == "node":
                        item["conditions"].extend(x.strip() for x in row.get("conditions", "").split("|") if x.strip())
                        # Node interventions are a deterministic fallback only when no drug edge exists.
                        if not item["raw"]:
                            item["raw"].extend(x.strip() for x in row.get("interventions", "").split("|") if x.strip())
        records = {
            nct: TrialContextRecord(
                nct_id=nct,
                genes=tuple(dict.fromkeys(v["genes"])),
                conditions=tuple(dict.fromkeys(v["conditions"])),
                interventions_raw=tuple(dict.fromkeys(v["raw"])),
                interventions_normalized=tuple(dict.fromkeys(v["normalized"])),
                provenance={"nct_id": nct, "source_root": str(root), "source_files": dict(source_files),
                            "source_file_sha256": dict(source_hashes),
                            "record_hash": hashlib.sha256(json_bytes(v)).hexdigest()},
            ) for nct, v in groups.items()
        }
        return cls(records, {"root": str(root), "files": {k: str(p) for k, p in files.items() if p.is_file()}})

    def lookup(self, nct: Any) -> TrialContextRecord | None:
        normalized = normalize_nct(nct)
        return self._records.get(normalized) if normalized else None


def json_bytes(value: Any) -> bytes:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@lru_cache(maxsize=1)
def load_trial_context_index() -> TrialContextIndex:
    return TrialContextIndex.from_directory(_default_root())


def candidate_nct(candidate: dict[str, Any]) -> str | None:
    for identifier in candidate.get("document_identifiers") or []:
        if isinstance(identifier, dict) and identifier.get("nct"):
            return normalize_nct(identifier["nct"])
    return None


def enrich_trial_candidate(candidate: dict[str, Any]) -> tuple[dict[str, Any], str]:
    nct = candidate_nct(candidate)
    record = load_trial_context_index().lookup(nct)
    if record is None:
        return candidate, "TRIAL_CONTEXT_MALFORMED" if nct is None else "TRIAL_CONTEXT_MISSING"
    enriched = dict(candidate)
    enriched["trial_context"] = {
        "nct_id": record.nct_id,
        "genes": record.genes,
        "conditions": record.conditions,
        "interventions_raw": record.interventions_raw,
        "interventions_normalized": record.interventions_normalized,
        "provenance": record.provenance,
        "retrieval_only": True,
    }
    return enriched, "TRIAL_CONTEXT_AVAILABLE"
