"""Genera gli artefatti della fase di binding del retriever V3.

Lo script non decide niente: esegue i due backend, misura, e scrive. Ogni valore
degli artefatti viene da una esecuzione, non da una costante ricopiata — un
artefatto che dichiarasse un conteggio senza averlo misurato non sarebbe una
prova di niente.

L'isolamento del percorso legacy viene misurato in un processo separato. E'
l'unico modo di dirlo davvero: dentro questo processo il modulo del retriever V3
e' gia' importato, e osservare `sys.modules` qui non direbbe nulla su cosa una
run legacy carica per conto proprio.

    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/build_retriever_binding_1_4.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from backend.pipeline.evidence.retrieval import diagnostics as DIAG
from backend.pipeline.evidence.retrieval import v3_backend as V3
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.retrieval.backends import (
    BACKEND_LEGACY,
    BACKEND_QUALIFIED_CLAIM_V3,
    backend_selection_contract,
)
from backend.pipeline.evidence.retrieval.legacy_backend import (
    LEGACY_CORPUS,
    LEGACY_SCORING_CONFIG,
    LegacyEvidenceRetrieverAdapter,
)
from backend.pipeline.evidence.retrieval.pipeline import (
    EvidenceRetrievalPipeline,
    pipeline_binding_manifest,
)
from backend.pipeline.evidence.retrieval.v3_scoring import scoring_contract
from benchmarks.mtb_evidence.evaluation import retriever_binding_1_4 as BINDING
from benchmarks.mtb_evidence.evaluation import retriever_binding_reports as REPORTS

REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT = REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "retriever_binding_1_4"

# Il probe gira in un interprete pulito: importa soltanto la pipeline, esegue una
# query sul backend legacy e riporta quali moduli del corpus V3 sono finiti in
# `sys.modules`. Se il binding fosse un import a livello di modulo, l'elenco non
# sarebbe vuoto.
ISOLATION_PROBE = """
import json, sys
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline

pipeline = EvidenceRetrievalPipeline()
pipeline.run(
    {
        "query_id": "ISO-01",
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}],
        "disease": "NSCLC",
        "disease_aliases": ["Lung Non-small Cell Carcinoma"],
    },
    retrieval_backend="legacy",
)
watched = (
    "backend.pipeline.evidence.corpus.loader",
    "backend.pipeline.evidence.retrieval.v3_backend",
    "backend.pipeline.evidence.retrieval.v3_objects",
)
print(json.dumps({
    "default_backend": pipeline.default_backend,
    "instantiated_backends": list(pipeline.instantiated_backends()),
    "imported": sorted(name for name in watched if name in sys.modules),
}))
"""


def digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def isolation_probe() -> dict[str, Any]:
    """Esegue il probe in un processo separato e ne legge l'esito."""
    completed = subprocess.run(
        [sys.executable, "-c", ISOLATION_PROBE],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**_env(), "PYTHONPATH": str(REPO_ROOT)},
        check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pipeline = EvidenceRetrievalPipeline()

    # --- percorso legacy, prima di ogni cosa V3 -----------------------------
    direct = QualifiedEvidenceRetriever.from_corpus(
        LEGACY_CORPUS, scoring_config_path=LEGACY_SCORING_CONFIG
    )
    adapter = LegacyEvidenceRetrieverAdapter.from_corpus()
    direct_digests: dict[str, str] = {}
    adapter_digests: dict[str, str] = {}
    for query_id, payload in sorted(BINDING.LEGACY_QUERIES.items()):
        try:
            direct_digests[query_id] = digest(
                direct.retrieve(adapter.build_native_query(payload)).as_dict()
            )
            adapter_digests[query_id] = digest(adapter.retrieve(payload).as_dict())
        except Exception as error:  # noqa: BLE001 - una query rifiutata resta registrata
            marker = f"REJECTED:{type(error).__name__}"
            direct_digests[query_id] = marker
            adapter_digests[query_id] = marker

    loader_calls_after_legacy = V3.loader_invocations()
    probe = isolation_probe()

    # --- percorso V3 ---------------------------------------------------------
    regression = BINDING.regression_rows(pipeline)
    selection = BINDING.selection_rows()
    health = pipeline.backend(BACKEND_QUALIFIED_CLAIM_V3).health_check()
    provenance = pipeline.backend(BACKEND_QUALIFIED_CLAIM_V3).provenance_summary()

    diagnostics = DIAG.diagnose_all(
        BINDING.retrieval_queries(),
        pipeline=pipeline,
        legacy_queries=BINDING.LEGACY_QUERIES,
    )
    diagnostic_rows = [row.to_dict() for row in diagnostics]

    parity = BINDING.legacy_parity(
        pipeline,
        direct_digests=direct_digests,
        adapter_digests=adapter_digests,
        loader_invocations_after_legacy=loader_calls_after_legacy,
        legacy_modules_imported=probe["imported"],
    )
    parity["isolation_probe"] = probe

    flags = BINDING.readiness(
        regression=regression,
        selection=selection,
        parity=parity,
        diagnostics=diagnostic_rows,
        health=health,
    )

    manifest = {
        "backend_selection": backend_selection_contract(),
        "corpus_hash": health["corpus_hash"],
        "gate_execution_order": V3.gate_execution_order(),
        "phase": BINDING.PHASE,
        "pipeline_binding": pipeline_binding_manifest(),
        "provenance_summary": provenance,
        "queries": len(BINDING.REGRESSION_QUERIES),
        "readiness": flags,
        "scoring": scoring_contract(),
        "selection_cases": selection,
        "v3_retriever": V3.v3_retriever_contract(),
    }

    files = {
        "backend_selection_contract.json": BINDING.as_json(backend_selection_contract()),
        "dual_run_diagnostic.jsonl": DIAG.as_jsonl(diagnostics),
        "gate_execution_order.json": BINDING.as_json(V3.gate_execution_order()),
        "legacy_parity.json": BINDING.as_json(parity),
        "retriever_binding_manifest.json": BINDING.as_json(manifest),
        "v3_query_schema.json": BINDING.as_json(BINDING.query_schema()),
        "v3_regression_queries.jsonl": BINDING.as_jsonl(BINDING.REGRESSION_QUERIES),
        "v3_regression_results.jsonl": BINDING.as_jsonl(regression),
        "v3_retrieval_result_schema.json": BINDING.as_json(RESULT.result_schema()),
        "v3_retriever_contract.json": BINDING.as_json(V3.v3_retriever_contract()),
        "V3_RETRIEVER_ARCHITECTURE.md": REPORTS.architecture(manifest),
        "LEGACY_VS_V3_BINDING.md": REPORTS.binding(manifest, parity),
        "EXPLORATORY_RERUN_READINESS.md": REPORTS.readiness(
            manifest, regression, diagnostic_rows
        ),
    }
    for name, body in sorted(files.items()):
        (OUTPUT / name).write_text(body, encoding="utf-8")
        print(f"scritto {name}")

    print()
    print(json.dumps(flags, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
