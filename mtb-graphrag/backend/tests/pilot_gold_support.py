"""Finzioni condivise fra i test unitari del pilot e quelli sul gold.

Stanno qui perche' la separazione fisica fra suite core e suite gold non
duplichi un client di grafo finto. Il modulo non contiene test e non apre
nessun ingresso esterno.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from benchmarks.mtb_evidence.pilot.audit_lib import report, second_review
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import (
    AliasValidationError,
    alias_manifest,
    build_alias_table,
)
from benchmarks.mtb_evidence.pilot.audit_lib.classify import (
    ADJUVANT_RESECTED,
    FIRST_LINE_ADVANCED,
    INSUFFICIENT_CONTEXT,
    NOT_MODELLED_QUALIFIERS,
    POST_PROGRESSION_T790M,
    TEXT_HEURISTIC,
    alteration_types,
    classify_setting,
    classify_variant_form,
    mentions,
    qualifier_status,
)
from benchmarks.mtb_evidence.pilot.audit_lib.compare import (
    FULL,
    PARTIAL,
    UNMATCHED,
    compare_case,
    graph_claim_from_record,
    match_claim,
)
from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    DIFFERENT_SPECIFICITY,
    IDENTICAL,
    SAME_ENTITY,
    disease_relation,
    diseases_match,
    split_disease,
)
from benchmarks.mtb_evidence.pilot.audit_lib.gold import (
    GoldParseError,
    load_gold,
    parse_gold_lines,
)
from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import (
    GraphUnavailable,
    Neo4jGraphClient,
    _is_connectivity_error,
)
from benchmarks.mtb_evidence.pilot.audit_lib.normalize import (
    norm_drug,
    norm_nct,
    norm_nct_set,
    norm_pmid,
    norm_pmid_set,
    norm_text,
)
from benchmarks.mtb_evidence.pilot.audit_lib.queries import n1_rmi2
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (
    REDACTED,
    canonical_json,
    fingerprint,
    sanitize_uri,
    scrub,
    secret_values,
    write_json,
    write_jsonl,
    write_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PILOT_ROOT = PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "pilot"

class _ScriptedGraphClient:
    """Client di grafo finto: risponde in base a un frammento del testo Cypher."""

    def __init__(self, responses=None, default=None):
        self._responses = list(responses or [])
        self._default = list(default or [])
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher, params=None):
        self.calls.append((cypher, dict(params or {})))
        for needle, records in self._responses:
            if needle in cypher:
                return [dict(record) for record in records]
        return [dict(record) for record in self._default]


def _gold_claim(**overrides):
    from benchmarks.mtb_evidence.pilot.audit_lib.gold import _parse_claim

    payload = {
        "claim_id": "T-C1",
        "case_id": "T",
        "subject": "EGFR L858R",
        "relation": "predicts benefit from first-line",
        "object": "osimertinib",
        "disease": "advanced NSCLC",
        "direction": "supports",
        "mandatory_qualifiers": "previously untreated",
        "pmid": "29151359",
        "nct_id": "NCT02296125",
    }
    payload.update(overrides)
    return _parse_claim(payload, "T")


def _graph_record(**overrides):
    payload = {
        "record_id": "evidence:1",
        "molecular_profile": "EGFR L858R",
        "significance": "Sensitivity/Response",
        "evidence_direction": "Supports",
        "disease": "Lung Non-small Cell Carcinoma",
        "citation_id": ["29151359"],
        "evidence_statement": "Previously untreated advanced NSCLC treated first-line.",
        "drug": "OSIMERTINIB",
    }
    payload.update(overrides)
    return payload


