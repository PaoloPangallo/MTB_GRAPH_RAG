"""Perimetro, percorsi e lettori condivisi dell'audit pre-promozione.

Un solo modulo conosce i path. Gli altri ricevono strutture gia' lette, cosi'
l'audit resta eseguibile su una copia del repository e nessun modulo puo'
aprire per sbaglio un artefatto che la fase dichiara di non leggere.

La regola che questo modulo rende meccanica e' una sola: **il gold non viene
mai aperto**. `GOLD_PATHS` esiste per essere confrontato con i path realmente
letti, non per essere usato come sorgente.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

PHASE = "pre-promotion-audit/1.3"
AUDIT_VERSION = "pre_promotion_audit/1.0"
AUDITED_REPOSITORY = "qualified_claim_repository/1.3"
REVIEWER_ROLE = "author_pre_promotion_auditor"
REVIEW_INDEPENDENCE = "non_independent"
REVIEW_STATUS = "first_review_complete"
PROPAGATION_POLICY = "prototype_only"

START_SHA = "bdc88f12ffb0f4f4ec6c01e6a7db9fd7dd7c97a9"

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"

SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V12 = V3 / "diagnostic_disease_scope_narrowing_shadow"
SHADOW_V13 = V3 / "integrated_shadow_repository_1_3"
TERMINOLOGY = V3 / "terminology_mapping_closure"
DISEASE_POLICY = V3 / "disease_hierarchy_policy"
ADJUDICATION = V3 / "multi_intervention_adjudication"
CORPUS = V3 / "qualification_corpus_v2"

DEFAULT_OUTPUT = V3 / "pre_promotion_audit_1_3"

# --- artefatti operativi congelati -------------------------------------------

OPERATIONAL_CORPUS = "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl"
OPERATIONAL_LINKS = "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl"
OPERATIONAL_VIEWS = (
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl"
)

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/qualification.py",
    "backend/pipeline/evidence/qualified_disease_matching.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/v2_adapter.py",
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
    OPERATIONAL_CORPUS,
    OPERATIONAL_LINKS,
    OPERATIONAL_VIEWS,
)

# Ruolo dichiarato di ciascun artefatto operativo, perche' la readiness possa
# nominare cio' che ha verificato invece di elencare path.
OPERATIONAL_ROLES = {
    "adapter operativo": "backend/pipeline/evidence/v2_adapter.py",
    "corpus operativo": OPERATIONAL_CORPUS,
    "disease matcher operativo": "backend/pipeline/evidence/qualified_disease_matching.py",
    "qualification links": OPERATIONAL_LINKS,
    "qualification operativa": "backend/pipeline/evidence/qualification.py",
    "QualifiedEvidenceView": OPERATIONAL_VIEWS,
    "repository operativo": "backend/pipeline/evidence/repository.py",
    "retriever operativo": "backend/pipeline/evidence/qualified_retriever.py",
    "scoring operativo": "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "scoring config operativa": "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "disease matcher del pilot": "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
}

FROZEN_SHADOW_DIRS = {
    "shadow repository 1.0": "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
    "shadow repository 1.1": "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
    "shadow repository 1.2": (
        "benchmarks/mtb_evidence/v3/diagnostic_disease_scope_narrowing_shadow"
    ),
    "shadow repository 1.3": "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3",
    "terminology closure": "benchmarks/mtb_evidence/v3/terminology_mapping_closure",
    "disease hierarchy policy": "benchmarks/mtb_evidence/v3/disease_hierarchy_policy",
    "adjudication": "benchmarks/mtb_evidence/v3/multi_intervention_adjudication",
}

# Il bundle gold sta fuori dal package e non viene mai aperto. Il path e'
# dichiarato perche' l'assenza di lettura sia verificabile per confronto, non
# perche' serva a leggerlo.
GOLD_PATHS = (
    "MTB_Evidence_gold_pilot_v1_bundle",
    "benchmarks/mtb_evidence/evaluation/clinical_gold.py",
    "benchmarks/mtb_evidence/evaluation/snapshot_gold.py",
)

# --- file della 1.3 -----------------------------------------------------------

REPOSITORY_FILES = {
    "claims": "evidence_claims_v1_3.jsonl",
    "deprecated": "deprecated_claims_v1_3.jsonl",
    "diagnostic": "diagnostic_claims_v1_3.jsonl",
    "lineage": "claim_replacement_lineage_v1_3.jsonl",
    "link_plan": "qualification_link_regeneration_plan_v1_3.jsonl",
    "parents": "graph_evidence_parents_v1_3.jsonl",
    "prognostic": "prognostic_claims_v1_3.jsonl",
    "therapeutic": "therapeutic_claims_v1_3.jsonl",
    "unresolved": "unresolved_associations_v1_3.jsonl",
    "unsupported": "unsupported_associations_v1_3.jsonl",
    "view_plan": "qualified_view_regeneration_plan_v1_3.jsonl",
}

MANIFEST_FILE = "repository_v1_3_manifest.json"
TERMINOLOGY_REGISTRY_FILE = "terminology_registry_v1_3.json"


class AuditScopeError(RuntimeError):
    """L'audit ha tentato di uscire dal proprio perimetro."""


def sha256_file(path: Path) -> str:
    """L'impronta di un file, come gli artefatti congelati la registrano.

    Per quasi tutti i file sono i byte cosi' come stanno. Per gli otto sorgenti
    che l'erratum registra e' l'impronta storica: quelle fasi la misurarono nella
    forma CRLF di una macchina Windows, e un checkout pulito consegna LF. Senza
    questa mediazione rigenerare uno di quegli artefatti produrrebbe un digest
    diverso da quello committato, e dodici artefatti di otto fasi chiuse
    smetterebbero di essere riproducibili.

    La sostituzione vale solo per i path registrati e solo finche' il loro
    contenuto e' quello che l'erratum descrive: vedi `legacy_hash_erratum`.
    """
    from benchmarks.mtb_evidence.evaluation import legacy_hash_erratum as ERRATUM

    return ERRATUM.recorded_sha256(path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_tree(directory: Path) -> str:
    """Hash di una directory: elenco ordinato `path:hash`, non byte concatenati.

    L'ordinamento per path rende l'hash indipendente dall'ordine di
    enumerazione del filesystem, che su piattaforme diverse non e' lo stesso.
    """
    directory = Path(directory)
    if not directory.exists():
        raise AuditScopeError(f"directory congelata assente: {directory}")
    rows = [
        f"{item.relative_to(directory).as_posix()}:{sha256_file(item)}"
        for item in sorted(directory.rglob("*"))
        if item.is_file() and "__pycache__" not in item.parts
    ]
    return sha256_text("\n".join(rows))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_repository(root: Path = SHADOW_V13) -> dict[str, Any]:
    """La 1.3 letta dai file, non dal manifest.

    Il manifest viene caricato accanto ai dati e non al posto loro: serve a
    essere *confrontato* con cio' che i file dicono, ed e' l'unico uso che
    l'audit ne fa.
    """
    root = Path(root)
    if not root.exists():
        raise AuditScopeError(f"repository shadow 1.3 assente: {root}")
    payload: dict[str, Any] = {
        name: read_jsonl(root / filename)
        for name, filename in REPOSITORY_FILES.items()
    }
    payload["manifest"] = read_json(root / MANIFEST_FILE)
    payload["terminology_registry"] = read_json(root / TERMINOLOGY_REGISTRY_FILE)
    return payload


def frozen_hashes(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Impronta degli artefatti che la fase dichiara di non toccare."""
    repo_root = Path(repo_root)
    return {
        "files": {
            role: {
                "path": path,
                "sha256": sha256_file(repo_root / path),
            }
            for role, path in sorted(OPERATIONAL_ROLES.items())
        },
        "trees": {
            role: {
                "path": path,
                "sha256": sha256_tree(repo_root / path),
            }
            for role, path in sorted(FROZEN_SHADOW_DIRS.items())
        },
    }


def gold_tree_hash(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Impronta del bundle gold, calcolata sui byte e senza deserializzare nulla.

    Un checksum non e' una lettura del contenuto: dimostra che il bundle non e'
    cambiato senza che una sola riga di gold entri nel ragionamento dell'audit.
    La distinzione e' registrata nell'artefatto perche' non vada perduta.
    """
    bundle = repo_root.parent / "MTB_Evidence_gold_pilot_v1_bundle"
    return {
        "bundle_present": bundle.exists(),
        "bundle_path": "MTB_Evidence_gold_pilot_v1_bundle",
        "checksum_only_no_deserialization": True,
        "gold_records_read": 0,
        "sha256": sha256_tree(bundle) if bundle.exists() else None,
        "used_for_any_decision": False,
    }


def paths_read(paths: Iterable[str]) -> list[str]:
    """Path realmente letti, ordinati, per il manifest dell'audit."""
    return sorted(dict.fromkeys(str(path) for path in paths))


def gold_paths_touched(read: Sequence[str]) -> list[str]:
    return sorted(
        path for path in read if any(path.startswith(gold) for gold in GOLD_PATHS)
    )


def canonical_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def canonical_jsonl(
    rows: Sequence[Mapping[str, Any]], *, key: str | Sequence[str]
) -> str:
    keys = (key,) if isinstance(key, str) else tuple(key)

    def sort_key(row: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(str(row.get(field) or "") for field in keys)

    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in sorted(rows, key=sort_key)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


__all__ = [
    "ADJUDICATION",
    "AUDITED_REPOSITORY",
    "AUDIT_VERSION",
    "CORPUS",
    "DEFAULT_OUTPUT",
    "DISEASE_POLICY",
    "FROZEN_SHADOW_DIRS",
    "GOLD_PATHS",
    "MANIFEST_FILE",
    "OPERATIONAL_ARTIFACTS",
    "OPERATIONAL_ROLES",
    "OPERATIONAL_VIEWS",
    "PHASE",
    "PROPAGATION_POLICY",
    "REPOSITORY_FILES",
    "REPO_ROOT",
    "REVIEWER_ROLE",
    "REVIEW_INDEPENDENCE",
    "REVIEW_STATUS",
    "SHADOW_V10",
    "SHADOW_V11",
    "SHADOW_V12",
    "SHADOW_V13",
    "START_SHA",
    "TERMINOLOGY",
    "V3",
    "AuditScopeError",
    "canonical_dumps",
    "canonical_jsonl",
    "frozen_hashes",
    "gold_paths_touched",
    "gold_tree_hash",
    "load_repository",
    "paths_read",
    "read_json",
    "read_jsonl",
    "sha256_file",
    "sha256_text",
    "sha256_tree",
]
