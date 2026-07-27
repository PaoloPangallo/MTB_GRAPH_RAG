"""Promuove il repository shadow 1.4 a corpus V3 prototipale versionato.

Lo script e' l'unico punto che conosce i percorsi. Legge la 1.4 e cio' che la
1.4 porta avanti senza riscriverlo — i parent e le associazioni della 1.3, il
lineage diagnostico della 1.2, i registri della terminology closure e della
disease hierarchy policy — e passa i record gia' letti al generatore, che non sa
da dove vengano.

La promozione non tocca nulla di operativo e non lo dichiara soltanto: gli hash
degli artefatti congelati vengono presi prima e dopo, e la query operativa viene
eseguita prima e dopo e confrontata per conteggio, serializzazione e digest. Il
gold viene hashato come albero e mai deserializzato.

Il registro prototipale e' aggiornato per ultimo e separatamente dal corpus. Un
registro scritto prima del rename descriverebbe una directory che non esiste
ancora.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import atomic_write as ATOMIC
from backend.pipeline.evidence.corpus import materialization as MAT
from backend.pipeline.evidence.corpus import promotion as PROMOTION
from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.corpus import prototype_registry as REGISTRY
from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_QUALIFIED_SOFT,
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from benchmarks.mtb_evidence.evaluation import required_fixes_1_4 as FIXES
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE

PHASE = CONTRACT.PHASE
START_SHA = CONTRACT.PROMOTION_COMMIT

V3 = SCOPE.V3
SHADOW_V12 = SCOPE.SHADOW_V12
SHADOW_V13 = SCOPE.SHADOW_V13
SHADOW_V14 = V3 / CONTRACT.SOURCE_SHADOW_DIRNAME
DISEASE_POLICY = SCOPE.DISEASE_POLICY

CORPUS_FINGERPRINT = "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"
OPERATIONAL_QUERY_BASELINE_SHA256 = (
    "af0389673a9a8b0566bce20bf68685b3abc04baf8542e183888d9a84cb365124"
)
SCORING_CONFIG = (
    SCOPE.REPO_ROOT / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
)

# Ogni artefatto sorgente, con il ruolo che ha nella promozione. L'elenco e'
# esplicito perche' il manifest possa dichiarare *cosa* e' stato letto invece di
# lasciarlo dedurre dal codice che lo ha letto.
SOURCE_FILES = {
    "claims 1.4": SHADOW_V14 / "evidence_claims_v1_4.jsonl",
    "disease match contract": DISEASE_POLICY / "disease_match_contract.json",
    "disease policy modes": DISEASE_POLICY / "disease_policy_modes.json",
    "disease relation definitions": DISEASE_POLICY / "disease_relation_definitions.json",
    "backward compatibility 1.4": SHADOW_V14 / "backward_compatibility_addendum.json",
    "formulation gate simulation 1.4": SHADOW_V14 / "formulation_gate_simulation.jsonl",
    "formulation registry 1.4": SHADOW_V14 / "formulation_registry_snapshot.jsonl",
    "lineage 1.3": SHADOW_V13 / "claim_replacement_lineage_v1_3.jsonl",
    "link plan 1.4": SHADOW_V14 / "qualification_link_plan_v1_4.jsonl",
    "manifest 1.4": SHADOW_V14 / "repository_v1_4_manifest.json",
    "parents 1.3": SHADOW_V13 / "graph_evidence_parents_v1_3.jsonl",
    "replacement map 1.2": SHADOW_V12 / "diagnostic_claim_replacement_map.jsonl",
    "deprecated 1.3": SHADOW_V13 / "deprecated_claims_v1_3.jsonl",
    "terminology registry 1.3": SHADOW_V13 / "terminology_registry_v1_3.json",
    "unresolved 1.3": SHADOW_V13 / "unresolved_associations_v1_3.jsonl",
    "unsupported 1.3": SHADOW_V13 / "unsupported_associations_v1_3.jsonl",
    "verified alias registry": DISEASE_POLICY / "verified_alias_registry_snapshot.json",
    "view plan 1.3": SHADOW_V13 / "qualified_view_regeneration_plan_v1_3.jsonl",
}


class PromotionScriptError(RuntimeError):
    """La promozione non puo' partire dallo stato in cui trova il repository."""


# --------------------------------------------------------------------------
# precondizioni
# --------------------------------------------------------------------------


def check_preconditions() -> dict[str, Any]:
    """La 1.4 e' pronta, integra e non e' stata toccata da questa fase."""
    manifest = SCOPE.read_json(SOURCE_FILES["manifest 1.4"])
    readiness = manifest["readiness"]
    required = (
        "shadow_repository_v1_4_ready",
        "required_promotion_fixes_resolved",
        "corpus_promotion_ready",
    )
    not_ready = [key for key in required if not readiness.get(key)]
    if not_ready:
        raise PromotionScriptError(f"la 1.4 non e' pronta: {not_ready}")
    findings = {
        key: readiness[key]
        for key in ("critical_findings", "major_findings", "minor_findings")
    }
    if any(findings.values()):
        raise PromotionScriptError(f"finding aperti nella 1.4: {findings}")

    recomputed = {
        name: SCOPE.sha256_file(SHADOW_V14 / name)
        for name in manifest["artifact_sha256"]
    }
    diverged = sorted(
        name
        for name, digest in manifest["artifact_sha256"].items()
        if recomputed.get(name) != digest
    )
    if diverged:
        raise PromotionScriptError(f"artefatti 1.4 divergenti dal manifest: {diverged}")

    policy = manifest["policy"]
    if policy["unknown_policy_mode_behavior"] != CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR:
        raise PromotionScriptError("la 1.4 non dichiara il rifiuto delle modalita' ignote")
    if policy["default_policy_mode"] != CONTRACT.DEFAULT_POLICY_MODE:
        raise PromotionScriptError("la default policy mode della 1.4 non e' strict_verified")

    return {
        "findings": findings,
        "readiness": {key: readiness[key] for key in required},
        "shadow_1_4_artifacts_verified": len(recomputed),
    }


def source_hashes() -> dict[str, str]:
    return {
        role: SCOPE.sha256_file(path) for role, path in sorted(SOURCE_FILES.items())
    }


def load_sources() -> MAT.Sources:
    """I record letti dagli artefatti shadow, senza nessuna riscrittura."""
    link_plan = SCOPE.read_jsonl(SOURCE_FILES["link plan 1.4"])
    if len(link_plan) != CONTRACT.EXPECTED_LINK_ACTIONS:
        raise PromotionScriptError(
            f"il piano di link ha {len(link_plan)} azioni invece di "
            f"{CONTRACT.EXPECTED_LINK_ACTIONS}"
        )
    if any(action.get("schema_version") != FIXES.LINK_PLAN_SCHEMA_VERSION for action in link_plan):
        raise PromotionScriptError("il piano di link non e' sullo schema normalizzato 1.1")

    view_plan = SCOPE.read_jsonl(SOURCE_FILES["view plan 1.3"])
    if len(view_plan) != CONTRACT.EXPECTED_VIEW_ACTIONS:
        raise PromotionScriptError(
            f"il piano di view ha {len(view_plan)} azioni invece di "
            f"{CONTRACT.EXPECTED_VIEW_ACTIONS}"
        )

    return MAT.Sources(
        claims=tuple(SCOPE.read_jsonl(SOURCE_FILES["claims 1.4"])),
        parents=tuple(SCOPE.read_jsonl(SOURCE_FILES["parents 1.3"])),
        deprecated=tuple(SCOPE.read_jsonl(SOURCE_FILES["deprecated 1.3"])),
        unsupported=tuple(SCOPE.read_jsonl(SOURCE_FILES["unsupported 1.3"])),
        unresolved=tuple(SCOPE.read_jsonl(SOURCE_FILES["unresolved 1.3"])),
        lineage_rows=tuple(SCOPE.read_jsonl(SOURCE_FILES["lineage 1.3"])),
        diagnostic_replacements=tuple(
            SCOPE.read_jsonl(SOURCE_FILES["replacement map 1.2"])
        ),
        terminology_registry=SCOPE.read_json(SOURCE_FILES["terminology registry 1.3"]),
        formulation_registry=tuple(
            SCOPE.read_jsonl(SOURCE_FILES["formulation registry 1.4"])
        ),
        formulation_gate_simulation=tuple(
            SCOPE.read_jsonl(SOURCE_FILES["formulation gate simulation 1.4"])
        ),
        salt_claims_leaving_primary=tuple(
            SCOPE.read_json(SOURCE_FILES["backward compatibility 1.4"])[
                "formulation_behaviour_change"
            ]["claims_leaving_primary_bucket"]
        ),
        disease_relation_definitions=SCOPE.read_json(
            SOURCE_FILES["disease relation definitions"]
        ),
        disease_policy_modes=SCOPE.read_json(SOURCE_FILES["disease policy modes"]),
        disease_match_contract=SCOPE.read_json(SOURCE_FILES["disease match contract"]),
        verified_alias_registry=SCOPE.read_json(
            SOURCE_FILES["verified alias registry"]
        ),
        link_plan=tuple(link_plan),
        view_plan=tuple(view_plan),
        source_file_sha256=source_hashes(),
        source_shadow_sha256=SCOPE.sha256_tree(SHADOW_V14),
    )


# --------------------------------------------------------------------------
# integrita' operativa
# --------------------------------------------------------------------------


def frozen_snapshot() -> dict[str, Any]:
    frozen = SCOPE.frozen_hashes()
    frozen["trees"]["pre-promotion audit 1.3"] = {
        "path": "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3",
        "sha256": SCOPE.sha256_tree(V3 / "pre_promotion_audit_1_3"),
    }
    frozen["trees"]["shadow repository 1.4"] = {
        "path": f"benchmarks/mtb_evidence/v3/{CONTRACT.SOURCE_SHADOW_DIRNAME}",
        "sha256": SCOPE.sha256_tree(SHADOW_V14),
    }
    return frozen


def operational_query() -> dict[str, Any]:
    """La query operativa, eseguita sul corpus V2 e sul retriever non modificato."""
    retriever = QualifiedEvidenceRetriever.from_corpus(
        SCOPE.CORPUS, scoring_config_path=SCORING_CONFIG
    )
    query = QualifiedRetrievalQuery(
        query_id="scope-narrowing-operational-parity",
        disease="Non-small cell lung cancer",
        disease_aliases=("Lung Non-small Cell Carcinoma",),
        biomarkers=(QueryBiomarker(gene="ALK"),),
        top_k=20,
        mode=MODE_QUALIFIED_SOFT,
        corpus_fingerprint=CORPUS_FINGERPRINT,
    )
    output = retriever.retrieve(query)
    text = (
        json.dumps(
            output.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    )
    return {
        "query_id": "scope-narrowing-operational-parity",
        "result_count": len(output.all_results),
        "serialization_length": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def integrity_report(
    *,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    query_before: Mapping[str, Any],
    query_after: Mapping[str, Any],
) -> dict[str, Any]:
    changed = [
        {
            "after": after[group][role]["sha256"],
            "before": entry["sha256"],
            "path": entry["path"],
            "role": role,
        }
        for group in ("files", "trees")
        for role, entry in sorted(before[group].items())
        if after[group][role]["sha256"] != entry["sha256"]
    ]
    return {
        "all_frozen_artifacts_unchanged": not changed,
        "changed": changed,
        "frozen_sha256": {
            role: entry["sha256"] for role, entry in sorted(after["files"].items())
        },
        "frozen_tree_sha256": {
            role: entry["sha256"] for role, entry in sorted(after["trees"].items())
        },
        "gold": SCOPE.gold_tree_hash(),
        "operational_query": {
            "after": dict(query_after),
            "baseline_sha256": OPERATIONAL_QUERY_BASELINE_SHA256,
            "before": dict(query_before),
            "matches_baseline": query_after["sha256"]
            == OPERATIONAL_QUERY_BASELINE_SHA256,
            "parity": query_before == query_after,
        },
    }


# --------------------------------------------------------------------------
# promozione
# --------------------------------------------------------------------------


def promote(
    *,
    corpus_path: Path,
    registry_path: Path,
    fail_at: str | None = None,
) -> dict[str, Any]:
    """La sequenza completa, dallo snapshot al registro."""
    preconditions = check_preconditions()
    before = frozen_snapshot()
    query_before = operational_query()

    sources = load_sources()
    artifacts = PROMOTION.build_artifacts(sources)

    outcome = ATOMIC.write_corpus_atomically(
        corpus_path,
        artifacts,
        validate=PROMOTION.validate_written_corpus,
        manifest_name=CONTRACT.MANIFEST_FILE,
        fail_at=fail_at,
        # La copia messa di lato durante lo scambio serve a ripristinare se il
        # secondo rename fallisce, e a nient'altro: una volta verificata la
        # nuova directory non ha piu' un ruolo, e conservarla lascerebbe nel
        # repository una seconda copia del corpus che nessun registro cita.
        keep_superseded=False,
    )

    entry = json.loads(artifacts["corpus_registry_entry.json"])
    registry = REGISTRY.register(REGISTRY.load(registry_path), entry)
    REGISTRY.save(registry, registry_path)

    after = frozen_snapshot()
    query_after = operational_query()
    integrity = integrity_report(
        before=before, after=after, query_before=query_before, query_after=query_after
    )
    if not integrity["all_frozen_artifacts_unchanged"]:
        raise PromotionScriptError(
            f"la promozione ha modificato artefatti congelati: {integrity['changed']}"
        )
    if not integrity["operational_query"]["parity"]:
        raise PromotionScriptError("la query operativa non e' identica prima e dopo")

    return {
        "artifacts": len(artifacts),
        "corpus_path": corpus_path.as_posix(),
        "file_sha256": outcome.sha256,
        "integrity": integrity,
        "preconditions": preconditions,
        "registry": registry,
        "registry_path": registry_path.as_posix(),
        "source_shadow_sha256": sources.source_shadow_sha256,
        "write_log": outcome.log,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=CONTRACT.PROMOTED_CORPUS)
    parser.add_argument("--registry", type=Path, default=CONTRACT.REGISTRY_PATH)
    args = parser.parse_args()

    result = promote(corpus_path=args.corpus, registry_path=args.registry)
    print(
        SCOPE.canonical_dumps(
            {
                "artifacts": result["artifacts"],
                "corpus_path": CONTRACT.PROMOTED_CORPUS_RELPATH,
                "operational_query_parity": result["integrity"]["operational_query"][
                    "parity"
                ],
                "operational_retriever_bound": result["registry"][
                    "operational_retriever_bound"
                ],
                "promotion_status": CONTRACT.PROMOTION_STATUS,
                "repository_version": CONTRACT.REPOSITORY_VERSION,
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
