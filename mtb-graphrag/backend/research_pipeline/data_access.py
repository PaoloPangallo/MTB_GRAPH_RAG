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
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

#: Radice del repository. Configurabile perché la profondità di questo file non
#: deve essere un'assunzione implicita: spostarlo non deve rompere i dati.
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]

_DGC = "benchmarks/mtb_evidence/document_grounded_claims"
_PILOT = "benchmarks/mtb_evidence/end_to_end_pipeline_pilot"
_EXPECTED_CANDIDATES_SHA256 = "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d"


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
    return _path(f"{_DGC}/graph_candidate_repository/2.0/candidates.jsonl")


def read_candidate_corpus_utf8() -> str:
    """Read the canonical candidate corpus only after identity validation.

    The corpus is a frozen UTF-8 JSONL artifact.  A checkout or transport
    transformation must be rejected before JSON parsing; permissive decoding
    would turn an artifact-integrity failure into altered scientific input.
    """
    path = candidates_path()
    if not path.is_file():
        raise FrozenDataUnavailable(f"dataset congelato assente: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != _EXPECTED_CANDIDATES_SHA256:
        raise FrozenDataUnavailable(
            "candidate corpus hash mismatch: "
            f"expected={_EXPECTED_CANDIDATES_SHA256} observed={digest}"
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
        "candidates": {row["candidate_id"]: row for row in iter_jsonl(candidates_path())},
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
