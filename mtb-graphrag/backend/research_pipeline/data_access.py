"""Accesso ai dati congelati del research runtime.

Risolve due rotture individuate in Fase B.

**Percorsi calcolati sulla posizione del file.** ``retrieval.py`` del pilot
faceva ``Path(__file__).resolve().parents[3]`` e da lì risolveva i propri
dataset: promuovere il modulo in ``backend/research_pipeline/`` cambia la
profondità e rompe silenziosamente il caricamento. Qui la radice è
configurazione esplicita.

**Aggancio al vecchio Claim Extractor.** ``run_pilot_v2.py`` importava
``_load_source_units`` e ``_load_supporting_maps`` da
``llm_claim_extractor/run_pilot.py``. Sono loader di dati, non logica di
estrazione: reimplementarli qui è la condizione per tenere il vecchio extractor
fuori dal flusso principale, come richiesto.

I dataset restano **in sola lettura** nella loro posizione in ``benchmarks/``:
``candidates.jsonl`` da solo pesa 72,5 MB e duplicarlo non avrebbe senso.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from functools import lru_cache
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

#: Radice del repository. Configurabile perché la profondità di questo file non
#: deve essere un'assunzione implicita: spostarlo non deve rompere i dati.
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]

_DGC = "benchmarks/mtb_evidence/document_grounded_claims"
_PILOT = "benchmarks/mtb_evidence/end_to_end_pipeline_pilot"
GRAPH_CANDIDATE_REPOSITORY_VERSION = "4.0"
_EXPECTED_CANDIDATES_SHA256 = "4e197764dff17cb396c5026338f07e001c0573e37bec9fb0f8a32e652b9d7edd"
_LEGACY_V2_CANDIDATES_SHA256 = "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d"


@dataclass(frozen=True)
class RuntimeCorpusSnapshot:
    repository_version: str
    candidate_sha256: str
    candidate_asset: str
    configuration_source: str
    terminology_configuration_source: str
    terminology_version: str
    terminology_sha256: str
    overlay_sha256: str
    source_manifest: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source_manifest"] = dict(self.source_manifest)
        return result


@lru_cache(maxsize=4)
def _runtime_snapshot(root: str, manifest_path: str, manifest_stat: tuple[int, int],
                      configuration_source: str) -> RuntimeCorpusSnapshot:
    # Only describe the pinned release; loading the corpus/registry remains
    # responsible for validating observed bytes. Never rehash 72 MB per query.
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    sources = {**manifest.get("source_hashes", {}),
               **{f"snapshot:{item['file']}": item["sha256"] for item in manifest.get("snapshots", [])}}
    return RuntimeCorpusSnapshot(
        GRAPH_CANDIDATE_REPOSITORY_VERSION, _EXPECTED_CANDIDATES_SHA256,
        f"{_DGC}/graph_candidate_repository/{GRAPH_CANDIDATE_REPOSITORY_VERSION}/candidates.jsonl",
        configuration_source,
        "RESEARCH_PIPELINE_TERMINOLOGY_MANIFEST" if os.getenv("RESEARCH_PIPELINE_TERMINOLOGY_MANIFEST") else "DEFAULT_PINNED_TERMINOLOGY_MANIFEST",
        manifest["registry_version"], manifest["registry_sha256"],
        manifest["overlay_sha256"], tuple(sorted(sources.items())),
    )


def runtime_corpus_snapshot() -> RuntimeCorpusSnapshot:
    """Immutable release description, including the pinned upstream sources."""
    from .terminology.loader import default_manifest_path

    manifest = default_manifest_path().resolve()
    stat = manifest.stat()
    configuration = "RESEARCH_PIPELINE_DATA_ROOT" if os.getenv("RESEARCH_PIPELINE_DATA_ROOT") else "DEFAULT_REPOSITORY_ROOT"
    return _runtime_snapshot(str(data_root()), str(manifest), (stat.st_mtime_ns, stat.st_size), configuration)


class FrozenDataUnavailable(RuntimeError):
    """Sollevata quando un dataset congelato manca.

    Non è recuperabile con un default: senza i dati la pipeline non ha nulla da
    osservare, e restituire un risultato vuoto lo farebbe apparire come un
    legittimo "nessuna candidate trovata".
    """


def data_root() -> Path:
    configured = os.getenv("RESEARCH_PIPELINE_DATA_ROOT")
    return Path(configured).expanduser().resolve() if configured else _DEFAULT_ROOT


def cache_root() -> Path:
    """Radice di ``AuthorizedDocumentCache``.

    Contiene i documenti integrali da cui vengono ri-parsate le SourceUnit ed è
    ignorata da git: è testo di terzi, non redatto. Oggi normalmente assente.
    """
    configured = os.getenv("RESEARCH_PIPELINE_CACHE_ROOT")
    return Path(configured).expanduser().resolve() if configured else data_root() / "data_cache/document_grounding"


def _path(relative: str) -> Path:
    return data_root() / relative


def candidates_path() -> Path:
    return _path(
        f"{_DGC}/graph_candidate_repository/{GRAPH_CANDIDATE_REPOSITORY_VERSION}/candidates.jsonl"
    )


def historical_candidates_path(version: str = "2.0") -> Path:
    """Path for explicitly requested historical/research replay artifacts."""
    if version != "2.0":
        raise ValueError(f"unsupported historical candidate repository: {version}")
    return _path(f"{_DGC}/graph_candidate_repository/{version}/candidates.jsonl")


def adapt_candidate_for_runtime(candidate: dict[str, Any]) -> dict[str, Any]:
    """Expose the v4 contract through the existing runtime candidate shape.

    The v4 artifact remains the source of truth and is never rewritten.  These
    aliases only preserve fields consumed by the unchanged retrieval/document
    stages; v4-native provenance remains available alongside them.
    """
    if candidate.get("materializer_version") != "gca-materializer/4.0":
        return candidate

    row = dict(candidate)
    context = row.get("context") or {}
    props = row.get("source_properties") or {}
    evidence = props.get("evidence") or {}
    profile = props.get("profile") or {}
    edge = props.get("edge") or {}
    trial = props.get("trial") or {}
    device = props.get("device") or {}
    subject = row.get("subject") or {}
    obj = row.get("object") or {}

    def entity(label: Any, kind: str, identifier: Any = None) -> dict[str, Any]:
        return {"id": identifier or label, "label": str(label), "type": kind}

    if "disease" not in row and (context.get("disease") or trial.get("conditions")):
        raw = context.get("disease") or trial.get("conditions")
        row["disease"] = [entity(raw, "Disease")]
    if "biomarkers" not in row:
        biomarker = profile.get("name")
        if subject.get("type") == "MolecularProfile" and biomarker:
            match = re.match(r"^([A-Za-z0-9-]+)\s+(.+)$", str(biomarker).strip())
            if match:
                row["biomarkers"] = [{
                    "id": subject.get("id") or biomarker,
                    "label": str(biomarker),
                    "type": "Variant",
                    "gene": match.group(1),
                    "alteration": match.group(2),
                    "specificity_level": "VARIANT",
                    "alteration_type": "UNKNOWN",
                }]
            else:
                row["biomarkers"] = [{
                    "id": subject.get("id") or biomarker,
                    "label": str(biomarker),
                    "type": "MolecularProfile",
                    "specificity_level": "MOLECULAR_PROFILE",
                    "alteration_type": "UNKNOWN",
                }]
        elif not biomarker and subject.get("type") in {"Gene", "GeneSymbol", "Variant"}:
            biomarker = subject.get("label")
        if not biomarker and obj.get("type") in {"Gene", "GeneSymbol", "Variant", "MolecularProfile"}:
            biomarker = obj.get("label")
        if not biomarker:
            biomarker = device.get("gene")
        if biomarker and "biomarkers" not in row:
            kind = "Variant" if any(token in str(biomarker).upper() for token in (" V", "MUT", "DEL", "AMP")) else "Gene"
            row["biomarkers"] = [entity(biomarker, kind)]
        elif "biomarkers" not in row:
            row["biomarkers"] = []
    if "interventions" not in row:
        intervention = edge.get("drug_name_raw") or edge.get("drug_name_normalized")
        if not intervention and obj.get("type") in {"Drug", "DrugName"}:
            intervention = obj.get("label")
        if not intervention and subject.get("type") in {"Drug", "DrugName"}:
            intervention = subject.get("label")
        row["interventions"] = [entity(intervention, "Drug")] if intervention else []
    if "companion_diagnostic" not in row and device:
        row["companion_diagnostic"] = {
            "name": device.get("device_name"),
            "identifier": device.get("device_id"),
            "associated_gene": device.get("gene"),
            "associated_drug": device.get("drug"),
            "platform": device.get("platform_type"),
            "specimen": device.get("specimen_types"),
        }
    if "direction" not in row and evidence.get("evidence_direction"):
        row["direction"] = evidence["evidence_direction"]
    if "evidence_scope" not in row and context.get("evidence_type"):
        row["evidence_scope"] = context["evidence_type"]
    if "evidence_record_ids" not in row:
        evidence_id = evidence.get("evidence_id")
        row["evidence_record_ids"] = [f"evidence:{evidence_id}"] if evidence_id else []
    if "edge_ids" not in row:
        row["edge_ids"] = [edge_id for ids in (row.get("edge_ids_by_dataset") or {}).values() for edge_id in ids]
    row.setdefault("candidate_version", GRAPH_CANDIDATE_REPOSITORY_VERSION)
    row.setdefault("materialization_rule_id", row.get("materialization_rule"))
    row.setdefault("materialized_at", None)
    return row


def read_candidate_corpus_utf8() -> str:
    """Read the canonical candidate corpus only after identity validation.

    The corpus is a frozen UTF-8 JSONL artifact.  A checkout or transport
    transformation must be rejected before JSON parsing; permissive decoding
    would turn an artifact-integrity failure into altered scientific input.
    """
    return _read_candidate_corpus_utf8(candidates_path(), _EXPECTED_CANDIDATES_SHA256)


def read_historical_candidate_corpus_utf8(version: str = "2.0") -> str:
    """Read a historical corpus only for research/replay callers."""
    expected = _LEGACY_V2_CANDIDATES_SHA256 if version == "2.0" else None
    if expected is None:
        raise ValueError(f"unsupported historical candidate repository: {version}")
    return _read_candidate_corpus_utf8(historical_candidates_path(version), expected)


def _read_candidate_corpus_utf8(path: Path, expected_digest: str) -> str:
    if not path.is_file():
        raise FrozenDataUnavailable(f"dataset congelato assente: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_digest:
        raise FrozenDataUnavailable(
            "candidate corpus hash mismatch: "
            f"expected={expected_digest} observed={digest}"
        )
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FrozenDataUnavailable(
            f"candidate corpus is not valid UTF-8 at byte offset {exc.start}"
        ) from exc


def evidence_bundles_path() -> Path:
    return _path(f"{_DGC}/evidence_bundle/evidence_bundles.jsonl")


def status_transitions_path() -> Path:
    return _path(f"{_DGC}/evidence_bundle/status_transitions.jsonl")


def document_manifest_path() -> Path:
    return _path(f"{_DGC}/authorized_document_cache_pilot/document_manifest.jsonl")


def source_unit_index_path() -> Path:
    return _path(f"{_DGC}/authorized_document_cache_pilot/source_unit_index.jsonl")


def frozen_enricher_runs_path() -> Path:
    return _path(f"{_PILOT}/paper_context_enricher_v2_runs.jsonl")


def frozen_validation_results_path() -> Path:
    return _path(f"{_PILOT}/paper_context_enricher_v2_validation_results.jsonl")


def frozen_paper_selection_path() -> Path:
    return _path(f"{_PILOT}/paper_selection_results.jsonl")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FrozenDataUnavailable(f"dataset congelato assente: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Lettura pigra, per i dataset che non stanno comodamente in memoria."""
    if not path.is_file():
        raise FrozenDataUnavailable(f"dataset congelato assente: {path}")
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_supporting_maps() -> dict[str, Any]:
    """Bundle, candidate, transizioni e manifest documentale.

    Reimplementa ``llm_claim_extractor.run_pilot._load_supporting_maps`` senza
    importarlo. Restituisce un dizionario invece di una tupla di quattro
    elementi: l'ordine posizionale era una fonte di errore silenziosa.
    """
    return {
        "bundles": read_jsonl(evidence_bundles_path()),
        "candidates": {
            row["candidate_id"]: adapt_candidate_for_runtime(row)
            for row in iter_jsonl(candidates_path())
        },
        "transitions": {row["candidate_id"]: row for row in read_jsonl(status_transitions_path())},
        "documents": read_jsonl(document_manifest_path()),
    }


@lru_cache(maxsize=1)
def load_source_unit_index() -> dict[str, dict[str, Any]]:
    """Indice delle SourceUnit: **solo locatori**, nessun testo.

    Verificato sul dataset: i campi sono ``source_unit_id``, ``document_id``,
    ``unit_type``, ``section``, ``paragraph_index``, ``sentence_index``,
    ``char_start``, ``char_end``, ``page``, ``content_hash`` e metadati del
    parser. È ciò che l'API può esporre senza esporre documento.
    """
    return {row["source_unit_id"]: row for row in iter_jsonl(source_unit_index_path())}


def document_cache_available() -> bool:
    """Se la cache documentale è presente, gli stage 6-10 sono eseguibili.

    Quando è assente il runtime non fallisce: rigioca gli artefatti congelati e
    lo dichiara. Ciò che non deve accadere è presentare un replay come
    esecuzione.
    """
    return cache_root().is_dir()


def load_source_units(documents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """SourceUnit **con testo**, ri-parsate dai documenti in cache.

    Reimplementa ``llm_claim_extractor.run_pilot._load_source_units`` senza
    importarlo, ma usa lo stesso ``AuthorizedDocumentCache`` con
    ``network=False``: nessun documento viene scaricato qui.
    """
    if not document_cache_available():
        raise FrozenDataUnavailable(
            f"cache documentale assente in {cache_root()}: le SourceUnit testuali "
            "non sono ricostruibili. Gli stage 6-10 useranno gli artefatti "
            "congelati, oppure ripopola la cache con il flag dedicato."
        )
    from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache

    cache = AuthorizedDocumentCache(root=cache_root(), network=False)
    units: dict[str, dict[str, Any]] = {}
    for document in documents:
        for unit in cache.source_units_for_record(dict(document)):
            units[unit["source_unit_id"]] = unit
    return units


def load_frozen_enricher_runs() -> list[dict[str, Any]]:
    """Le 7 chiamate reali all'enricher v2 registrate al commit ``6ee64c5``.

    Non sono mock: sono risposte reali del modello, con ``transport_result``,
    quote, ``source_unit_id``, ``prompt_version``, token e latenza. Rigiocarle
    mostra al relatore ciò che il modello ha davvero prodotto.
    """
    return read_jsonl(frozen_enricher_runs_path())


def describe_availability() -> dict[str, Any]:
    """Stato dei dataset, per la UI. Nessun percorso assoluto verso l'esterno."""
    checks = {
        "candidates": candidates_path(),
        "evidence_bundles": evidence_bundles_path(),
        "status_transitions": status_transitions_path(),
        "document_manifest": document_manifest_path(),
        "source_unit_index": source_unit_index_path(),
        "frozen_enricher_runs": frozen_enricher_runs_path(),
    }
    # ``stages_6_to_10_mode`` diceva ``FROZEN_REPLAY`` quando la cache mancava, e
    # descriveva un ripiego che il runtime non ha mai eseguito: senza cache la run
    # si arresta con ``DOCUMENT_CACHE_UNAVAILABLE``. Il campo dichiara ora
    # l'*eseguibilità* della catena documentale, che è ciò che una UI deve sapere.
    cache_available = document_cache_available()
    return {
        "datasets": {name: path.is_file() for name, path in checks.items()},
        "document_cache_available": cache_available,
        "stages_6_to_10_mode": "CANONICAL" if cache_available else "UNAVAILABLE",
        "stages_6_to_10_reason": (
            None if cache_available
            else "DOCUMENT_CACHE_UNAVAILABLE: la catena documentale non parte e "
                 "non ripiega su artefatti congelati"
        ),
    }
