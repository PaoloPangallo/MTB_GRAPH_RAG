"""Congelamento deterministico dei dataset della final evaluation.

Lo script è **offline e read-only**: non chiama modelli, non tocca la rete e non
scrive nulla fuori da ``evaluation/final_protocol/``. Produce tre artefatti:

``dataset_manifest.json``
    Inventario dei corpus con conteggi, provenance, sorgente del gold e
    classificazione dello split.

``dataset_hashes.json``
    SHA-256 di ogni file che compone un corpus, più un ``corpus_sha256``
    aggregato e un ``dataset_bundle_sha256`` complessivo.

``split_manifest.json``
    Appartenenza di ogni corpus a PILOT / DEVELOPMENT / INDEPENDENT /
    FINAL_TEST, con la motivazione e il componente eventualmente contaminato.

Nessun conteggio è scritto a mano: tutti i numeri derivano dalla lettura degli
artefatti. Se un file manca, lo script fallisce invece di stimare.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent

PROTOCOL_VERSION = "mtb-graphrag-final-evaluation/1.0"
RUNTIME_COMMIT = "f52bbf5920c14324953be849e666bc84571957e9"


class MissingArtifact(FileNotFoundError):
    """Un corpus dichiarato non esiste sul disco. Non esiste un default."""


# --------------------------------------------------------------------- hashing

def _sha256_file(path: Path) -> str:
    """SHA-256 con fine riga normalizzati a LF.

    Gli artefatti sono tutti testuali e git li memorizza con LF, mentre su
    Windows stanno su disco con CRLF. Senza normalizzazione lo stesso contenuto
    produrrebbe due hash diversi a seconda della piattaforma del clone, e il
    freeze non sarebbe verificabile da nessun altro. È lo stesso problema già
    registrato dall'audit di contaminazione come CF-01.
    """
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _corpus_hash(file_hashes: dict[str, str]) -> str:
    """Hash aggregato, indipendente dall'ordine di enumerazione del filesystem."""
    payload = "\n".join(f"{name}:{digest}" for name, digest in sorted(file_hashes.items()))
    return _sha256_text(payload)


# ----------------------------------------------------------------- lettura dati

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(relative: str) -> Path:
    path = REPO_ROOT / relative
    if not path.exists():
        raise MissingArtifact(f"artefatto dichiarato ma assente: {relative}")
    return path


def _files_of(paths: Iterable[str]) -> dict[str, str]:
    return {relative: _sha256_file(_resolve(relative)) for relative in sorted(paths)}


# ------------------------------------------------------------------- i corpus
#
# Ogni voce dichiara i file che COMPONGONO il corpus (input e gold), non i file
# di risultato: un risultato può essere rigenerato, un input no.

CORPORA: list[dict[str, Any]] = [
    {
        "corpus_id": "CASECONTEXT_ROBUSTNESS_35",
        "title": "CaseContext robustness benchmark",
        "files": [
            "evaluation/rq4_casecontext_robustness/benchmark.jsonl",
            "evaluation/rq4_casecontext_robustness/frozen_benchmark_manifest.json",
        ],
        "annotation_source": "AUTHORED_EXPECTATIONS_FROZEN_BEFORE_EXECUTION",
        "gold_kind": "PROGRAMMATIC_EXPECTED_PATH",
        "split": "DEVELOPMENT",
        "usable_for_final_eval": True,
        "final_role": "REGRESSION_AND_ROBUSTNESS_MATRIX",
        "contaminated_component": "pre-retrieval-eligibility-gate/1.0",
        "rationale": (
            "Gold congelato con SHA-256 prima della prima chiamata al parser "
            "(2026-08-06T14:32Z, esecuzione 14:43Z). Il Pre-Retrieval Eligibility "
            "Gate è però stato progettato alle 19:34Z dello stesso giorno in "
            "risposta esplicita a un fallimento osservato su questo benchmark "
            "(citato nel docstring di eligibility/gate.py). Il corpus resta "
            "valido come regression e robustness matrix, NON come generalizzazione "
            "su input mai visti dal gate."
        ),
    },
    {
        "corpus_id": "SOURCEUNIT_SELECTOR_INDEPENDENT_20",
        "title": "Independent SourceUnit selector corpus",
        "files": [
            "evaluation/sourceunit_selector_independent/candidate_inventory.jsonl",
            "evaluation/sourceunit_selector_independent/document_inventory.jsonl",
            "evaluation/sourceunit_selector_independent/gold_annotations.csv",
            "evaluation/sourceunit_selector_independent/gold_annotation_manifest.json",
            "evaluation/sourceunit_selector_independent/corpus_inventory.json",
            "evaluation/sourceunit_selector_independent/leakage_audit.json",
        ],
        "annotation_source": "SINGLE_HUMAN_PROTOCOL_PASS",
        "gold_kind": "HUMAN_ANNOTATED_RELEVANCE",
        "split": "INDEPENDENT",
        "usable_for_final_eval": True,
        "final_role": "PRIMARY_RETRIEVAL_GENERALIZATION_EVIDENCE",
        "contaminated_component": None,
        "rationale": (
            "Selector congelato alle 2026-08-08T09:11Z; corpus e gold congelati "
            "alle 10:59Z; valutazione alle 11:00Z. selector_code_modified=false e "
            "selector_weights_modified=false dopo la valutazione. Il leakage audit "
            "registra 0 accessi al gold durante l'inferenza. È l'unico corpus del "
            "progetto realmente esterno al design dei componenti."
        ),
    },
    {
        "corpus_id": "FROZEN_EVIDENCE_BUNDLES_25",
        "title": "Frozen evidence bundles (REPLAY)",
        "files": [
            "benchmarks/mtb_evidence/document_grounded_claims/evidence_bundle/evidence_bundles.jsonl",
            "benchmarks/mtb_evidence/document_grounded_claims/evidence_bundle/status_transitions.jsonl",
            "evaluation/sourceunit_selector/dataset.jsonl",
        ],
        "annotation_source": "BUNDLE_GOLD_SOURCE_UNITS",
        "gold_kind": "HUMAN_CURATED_BUNDLE_GOLD",
        "split": "DEVELOPMENT",
        "usable_for_final_eval": True,
        "final_role": "REPLAY_REPRODUCIBILITY_AND_SELECTOR_REGRESSION",
        "contaminated_component": "deterministic-sourceunit-selector/1.0 (feature design, K)",
        "rationale": (
            "Le feature del selector e il valore K=5 sono stati scelti osservando "
            "questo corpus (76 gold source unit su 25 bundle). Non può essere "
            "presentato come evidenza di generalizzazione del selector. Resta il "
            "corpus corretto per la riproducibilità REPLAY, perché la proprietà "
            "misurata lì è l'identità dell'output, non la qualità del ranking."
        ),
    },
    {
        "corpus_id": "AUTHORIZED_DOCUMENT_CACHE_43",
        "title": "Authorized document cache manifest",
        "files": [
            "benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/document_manifest.jsonl",
            "benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/source_unit_index.jsonl",
        ],
        "annotation_source": "OFFICIAL_API_ACQUISITION",
        "gold_kind": "OBJECTIVE_PROVENANCE_RECORD",
        "split": "DEVELOPMENT",
        "usable_for_final_eval": True,
        "final_role": "CACHE_HIT_MISS_AND_DEGRADATION_SUBSTRATE",
        "contaminated_component": None,
        "rationale": (
            "Non è un corpus di casi ma il substrato documentale: 43 documenti "
            "(40 disponibili, 3 con PMC_RESOLUTION_FAILED) e 3402 SourceUnit. "
            "Fornisce i denominatori di cache hit/miss e di degradazione ad "
            "abstract. Il gold è la provenienza registrata, non un giudizio."
        ),
    },
    {
        "corpus_id": "END_TO_END_PIPELINE_PILOT_5",
        "title": "End-to-end pipeline pilot cases",
        "files": [
            "benchmarks/mtb_evidence/end_to_end_pipeline_pilot/test_cases.json",
        ],
        "annotation_source": "AUTHORED_FROM_KNOWN_CANDIDATES",
        "gold_kind": "PROGRAMMATIC_EXPECTED_PATH",
        "split": "PILOT",
        "usable_for_final_eval": True,
        "final_role": "REGRESSION_ONLY",
        "contaminated_component": "orchestrator routing, dossier presentation",
        "rationale": (
            "Cinque casi costruiti a partire da candidate e bundle noti per "
            "guidare lo sviluppo della pipeline end-to-end. Sono i casi che hanno "
            "definito il comportamento atteso: vanno riportati come regression, "
            "mai come campione di valutazione."
        ),
    },
    {
        "corpus_id": "DOSSIER_NARRATOR_25",
        "title": "Dossier narrator benchmark",
        "files": [
            "evaluation/dossier_narrator/narrator_input_samples.jsonl",
            "evaluation/dossier_narrator/narrator_contract.json",
            "benchmarks/mtb_evidence/dossier_narrator/narrative_runs.jsonl",
        ],
        "annotation_source": "DETERMINISTIC_VERIFIER_PLUS_EMPTY_HUMAN_COLUMNS",
        "gold_kind": "PROGRAMMATIC_FIDELITY_CHECK",
        "split": "DEVELOPMENT",
        "usable_for_final_eval": True,
        "final_role": "NARRATIVE_VERIFIER_ABLATION_AND_REGRESSION",
        "contaminated_component": "narrative-lexicon/1.0",
        "rationale": (
            "Contaminazione documentata dagli stessi autori dell'artefatto: la "
            "prima esecuzione LIVE produsse 3 FAIL, il lexicon fu corretto e le "
            "STESSE narrative furono riverificate ottenendo 25/25. Il 25/25 è "
            "quindi un risultato post-tuning sullo stesso campione. Il corpus "
            "resta utilizzabile per l'ablation del Narrative Verifier, dove la "
            "misura è il delta FULL vs NO_VERIFIER sulle stesse narrative."
        ),
    },
    {
        "corpus_id": "NARRATOR_ADVERSARIAL_20",
        "title": "Narrator adversarial cases",
        "files": [
            "evaluation/dossier_narrator/adversarial_results.jsonl",
        ],
        "annotation_source": "AUTHORED_HOSTILE_INPUTS",
        "gold_kind": "PROGRAMMATIC_EXPECTED_REJECTION",
        "split": "DEVELOPMENT",
        "usable_for_final_eval": True,
        "final_role": "SAFETY_MATRIX_NARRATIVE_LAYER",
        "contaminated_component": "narrative-verifier/1.0",
        "rationale": (
            "Venti input ostili scritti insieme al verifier che devono bloccarli. "
            "Sono test di costruzione, non un campione indipendente: dimostrano "
            "che la classe di fallimento è coperta, non che sia esaustiva."
        ),
    },
    {
        "corpus_id": "QUOTE_VALIDATOR_BATTERY_14",
        "title": "Quote validator adversarial battery",
        "files": [
            "evaluation/pre_freeze/raw/G01_rq3_quote_battery.jsonl",
        ],
        "annotation_source": "AUTHORED_HOSTILE_INPUTS",
        "gold_kind": "PROGRAMMATIC_EXPECTED_ACCEPT_REJECT",
        "split": "DEVELOPMENT",
        "usable_for_final_eval": True,
        "final_role": "SAFETY_MATRIX_QUOTE_LAYER",
        "contaminated_component": "quote validator v2 reason codes",
        "rationale": (
            "Quattordici scenari con esito atteso ACCEPT/REJECT dichiarato prima "
            "dell'esecuzione, scritti però contro il validator esistente. Coprono "
            "la classe di fallimento richiesta dall'ablation C."
        ),
    },
    {
        "corpus_id": "GCA_REPOSITORY_2_0_46864",
        "title": "GraphCandidateAssertion repository 2.0 (runtime)",
        "files": [
            "benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/2.0/candidates.jsonl",
        ],
        "annotation_source": "DETERMINISTIC_MATERIALIZATION_FROM_FROZEN_CSV_EXPORT",
        "gold_kind": "OBJECTIVE_REDERIVED_GROUND_TRUTH",
        "split": "FINAL_TEST",
        "usable_for_final_eval": True,
        "final_role": "RQ1_FIDELITY_FULL_CORPUS_AND_NEGATIVE_POLARITY_SWEEP",
        "contaminated_component": None,
        "rationale": (
            "Il gold di RQ1 è ottenuto riderivando i path eleggibili dall'export "
            "CSV congelato con codice indipendente (evaluation/rq1/kg_source.py), "
            "senza rieseguire il materializzatore: non è un confronto tautologico. "
            "È l'unico corpus full-population del progetto e non ha campionamento, "
            "quindi non ammette leakage di selezione."
        ),
    },
    {
        "corpus_id": "GCA_REPOSITORY_3_0_SHADOW",
        "title": "GraphCandidateAssertion repository 3.0 (shadow)",
        "files": [
            "benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/3.0/candidates.jsonl",
            "benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/3.0/manifest.json",
        ],
        "annotation_source": "DETERMINISTIC_MATERIALIZATION_SHADOW",
        "gold_kind": "OBJECTIVE_REDERIVED_GROUND_TRUTH",
        "split": "FINAL_TEST",
        "usable_for_final_eval": True,
        "final_role": "RQ1_SHADOW_COMPARISON_ONLY_NOT_RUNTIME",
        "contaminated_component": None,
        "rationale": (
            "Il runtime a f52bbf5 legge 2.0 (backend/research_pipeline/data_access.py) "
            "e nessun modulo del runtime importa kg_retrieval_v3. Le proprietà di "
            "3.0 (polarità esplicita, regimi preservati, alterazioni composte) NON "
            "vanno attribuite al sistema valutato."
        ),
    },
]


def build() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()

    manifest_entries: list[dict[str, Any]] = []
    hash_entries: dict[str, Any] = {}
    split_entries: list[dict[str, Any]] = []

    for corpus in CORPORA:
        file_hashes = _files_of(corpus["files"])
        corpus_sha = _corpus_hash(file_hashes)
        counts = _counts_for(corpus["corpus_id"])

        manifest_entries.append({
            "corpus_id": corpus["corpus_id"],
            "title": corpus["title"],
            "paths": sorted(corpus["files"]),
            "counts": counts,
            "annotation_source": corpus["annotation_source"],
            "gold_kind": corpus["gold_kind"],
            "split": corpus["split"],
            "usable_for_final_eval": corpus["usable_for_final_eval"],
            "final_role": corpus["final_role"],
            "corpus_sha256": corpus_sha,
        })
        hash_entries[corpus["corpus_id"]] = {
            "corpus_sha256": corpus_sha,
            "files": file_hashes,
        }
        split_entries.append({
            "corpus_id": corpus["corpus_id"],
            "split": corpus["split"],
            "contaminated_component": corpus["contaminated_component"],
            "final_role": corpus["final_role"],
            "rationale": corpus["rationale"],
        })

    bundle_sha = _corpus_hash({
        entry["corpus_id"]: entry["corpus_sha256"] for entry in manifest_entries
    })

    dataset_manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "generated_at": generated_at,
        "runtime_modified": False,
        "corpora": manifest_entries,
        "dataset_bundle_sha256": bundle_sha,
    }
    dataset_hashes = {
        "protocol_version": PROTOCOL_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "generated_at": generated_at,
        "hash_algorithm": "sha256",
        "file_hash_rule": "sha256 of the file bytes with CRLF normalized to LF (platform-independent)",
        "corpus_hash_rule": "sha256 of the sorted 'relative_path:file_sha256' lines joined by \\n",
        "corpora": hash_entries,
        "dataset_bundle_sha256": bundle_sha,
    }
    split_manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "generated_at": generated_at,
        "split_definitions": {
            "PILOT": "casi che hanno guidato la costruzione della pipeline; solo regression",
            "DEVELOPMENT": "casi osservati prima del congelamento di almeno un componente che li riguarda; regression e ablation, mai generalizzazione",
            "INDEPENDENT": "gold congelato prima del congelamento del componente valutato e nessun accesso al gold durante l'inferenza",
            "FINAL_TEST": "popolazione completa senza campionamento, oppure gold riderivato indipendentemente dall'artefatto valutato",
        },
        "corpora": split_entries,
        "dataset_bundle_sha256": bundle_sha,
    }

    _write(OUT_DIR / "dataset_manifest.json", dataset_manifest)
    _write(OUT_DIR / "dataset_hashes.json", dataset_hashes)
    _write(OUT_DIR / "split_manifest.json", split_manifest)
    return dataset_manifest


def _counts_for(corpus_id: str) -> dict[str, Any]:
    """Conteggi letti dagli artefatti. Nessun numero è scritto a mano."""
    if corpus_id == "CASECONTEXT_ROBUSTNESS_35":
        rows = _read_jsonl(_resolve("evaluation/rq4_casecontext_robustness/benchmark.jsonl"))
        frozen = _read_json(_resolve("evaluation/rq4_casecontext_robustness/frozen_benchmark_manifest.json"))
        return {
            "n_cases": len(rows),
            "labels": frozen["categories"],
            "benchmark_sha256_declared": frozen["benchmark_sha256"],
            "frozen_at": frozen["frozen_at"],
        }

    if corpus_id == "SOURCEUNIT_SELECTOR_INDEPENDENT_20":
        inventory = _read_json(_resolve("evaluation/sourceunit_selector_independent/corpus_inventory.json"))
        gold = _read_json(_resolve("evaluation/sourceunit_selector_independent/gold_annotation_manifest.json"))
        per_case = gold["per_case"]
        labels: dict[str, int] = {}
        for counts in per_case.values():
            for label, value in counts.items():
                labels[label] = labels.get(label, 0) + value
        positive = sum(1 for c in per_case.values() if c.get("DIRECTLY_RELEVANT", 0) > 0)
        return {
            "n_cases": inventory["valid_pair_count"],
            "n_documents": inventory["document_count"],
            "n_source_units": gold["unit_count"],
            "labels": labels,
            "positive_cases": positive,
            "zero_direct_cases": inventory["valid_pair_count"] - positive,
            "pmc_fulltext_documents": inventory["pmc_fulltext_count"],
            "pubmed_abstract_documents": inventory["pubmed_abstract_count"],
            "gold_annotation_hash": inventory["gold_annotation_hash"],
            "pilot_candidate_overlap": len(inventory["overlap_with_pilot_candidates"]),
            "pilot_document_overlap": len(inventory["overlap_with_pilot_documents"]),
        }

    if corpus_id == "FROZEN_EVIDENCE_BUNDLES_25":
        bundles = _read_jsonl(_resolve(
            "benchmarks/mtb_evidence/document_grounded_claims/evidence_bundle/evidence_bundles.jsonl"))
        dataset = _read_jsonl(_resolve("evaluation/sourceunit_selector/dataset.jsonl"))
        candidates = {row.get("candidate_id") for row in dataset if row.get("candidate_id")}
        gold_units = sum(len(row.get("gold_source_unit_ids") or []) for row in dataset)
        return {
            "n_cases": len(dataset),
            "n_bundles": len(bundles),
            "n_candidates": len(candidates),
            "n_gold_source_units": gold_units,
        }

    if corpus_id == "AUTHORIZED_DOCUMENT_CACHE_43":
        docs = _read_jsonl(_resolve(
            "benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/document_manifest.jsonl"))
        units = _read_jsonl(_resolve(
            "benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/source_unit_index.jsonl"))
        availability: dict[str, int] = {}
        sources: dict[str, int] = {}
        for row in docs:
            availability[row["availability"]] = availability.get(row["availability"], 0) + 1
            sources[row["source"]] = sources.get(row["source"], 0) + 1
        return {
            "n_documents": len(docs),
            "n_source_units": len(units),
            "labels": {"availability": availability, "source": sources},
        }

    if corpus_id == "END_TO_END_PIPELINE_PILOT_5":
        cases = _read_json(_resolve("benchmarks/mtb_evidence/end_to_end_pipeline_pilot/test_cases.json"))
        statuses: dict[str, int] = {}
        for case in cases:
            status = (case.get("source_record") or {}).get("baseline_support_status", "UNSPECIFIED")
            statuses[status] = statuses.get(status, 0) + 1
        return {"n_cases": len(cases), "labels": {"baseline_support_status": statuses}}

    if corpus_id == "DOSSIER_NARRATOR_25":
        samples = _read_jsonl(_resolve("evaluation/dossier_narrator/narrator_input_samples.jsonl"))
        runs = _read_jsonl(_resolve("benchmarks/mtb_evidence/dossier_narrator/narrative_runs.jsonl"))
        strata: dict[str, int] = {}
        for row in samples:
            stratum = row.get("stratum") or row.get("case_class") or "UNSPECIFIED"
            strata[stratum] = strata.get(stratum, 0) + 1
        return {"n_cases": len(samples), "n_recorded_runs": len(runs), "labels": {"stratum": strata}}

    if corpus_id == "NARRATOR_ADVERSARIAL_20":
        rows = _read_jsonl(_resolve("evaluation/dossier_narrator/adversarial_results.jsonl"))
        families: dict[str, int] = {}
        expectations: dict[str, int] = {}
        for row in rows:
            families[row["family"]] = families.get(row["family"], 0) + 1
            expectations[row["expected"]] = expectations.get(row["expected"], 0) + 1
        return {"n_cases": len(rows), "labels": {"family": families, "expected": expectations}}

    if corpus_id == "QUOTE_VALIDATOR_BATTERY_14":
        rows = _read_jsonl(_resolve("evaluation/pre_freeze/raw/G01_rq3_quote_battery.jsonl"))
        expected: dict[str, int] = {}
        for row in rows:
            expected[row["expected"]] = expected.get(row["expected"], 0) + 1
        return {"n_cases": len(rows), "labels": {"expected": expected}}

    if corpus_id == "GCA_REPOSITORY_2_0_46864":
        rows = _read_jsonl(_resolve(
            "benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/2.0/candidates.jsonl"))
        rules: dict[str, int] = {}
        directions: dict[str, int] = {}
        with_pmid = 0
        for row in rows:
            rules[row["materialization_rule_id"]] = rules.get(row["materialization_rule_id"], 0) + 1
            direction = str(row.get("direction"))
            directions[direction] = directions.get(direction, 0) + 1
            if any(d.get("pmid") for d in (row.get("document_identifiers") or [])):
                with_pmid += 1
        return {
            "n_candidates": len(rows),
            "n_candidates_with_pmid": with_pmid,
            "labels": {"materialization_rule_id": rules, "direction": directions},
        }

    if corpus_id == "GCA_REPOSITORY_3_0_SHADOW":
        rows = _read_jsonl(_resolve(
            "benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/3.0/candidates.jsonl"))
        return {"n_candidates": len(rows), "runtime_default": False}

    raise KeyError(f"nessuna regola di conteggio per {corpus_id}")


def _write(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


if __name__ == "__main__":
    result = build()
    print(f"corpora: {len(result['corpora'])}")
    print(f"dataset_bundle_sha256: {result['dataset_bundle_sha256']}")
    for entry in result["corpora"]:
        print(f"  {entry['corpus_id']:<38} {entry['split']:<12} {entry['counts']}")
