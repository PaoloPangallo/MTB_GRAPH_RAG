"""Replay degli artefatti congelati del pilot. **RESEARCH / REGRESSION ONLY.**

Questo modulo non fa parte del runtime clinico-operativo e non è raggiungibile
da alcun percorso di prodotto:

- ``POST /api/v1/research/pipeline/runs`` non lo importa e non ha un campo che
  possa selezionarlo;
- ``RunStore`` non lo importa: i suoi provider sono soltanto quelli canonici;
- la console clinica non ha né un selettore di modalità né un'azione che apra
  una run registrata.

L'unico modo di arrivare qui è iniettarne gli adattatori in
``orchestrator.run_case(research_frozen_artifacts=True, call_parser_fn=…,
select_papers_fn=…, validate_fn=…)`` da un harness di test o di valutazione.
L'iniezione è verbosa di proposito: deve restare visibile, nella chiamata, che
si sta riproducendo un esperimento storico e non eseguendo la pipeline.

Perché resta. Riproducibilità. Gli esperimenti congelati devono continuare a
produrre esattamente ciò che produssero, e le proprietà «il replay non tocca la
rete» e «il replay non usa il selettore canonico» si dimostrano solo eseguendo
davvero questo percorso.

Perché nacque. ``paper_selection`` ammette un bundle solo se almeno una delle sue
SourceUnit ha testo (``paper_selection.py``, criterio ``TEXT_NOT_AVAILABLE_IN_CACHE``),
e il testo vive nella cache documentale, oggi assente. Rieseguire gli stage 8-10
in quelle condizioni produrrebbe zero paper selezionati e zero citazioni: un
esito tecnicamente corretto ma che rappresenterebbe male il sistema, perché il
pilot su quegli stessi casi ha prodotto 3 QUOTE, 2 accettate e 1 rigettata.

Cosa si rigioca e cosa no. Si rigiocano **soltanto** gli stage la cui esecuzione
richiede dati non più disponibili: selezione dei paper, chiamata all'enricher e
suo esito di validazione. Tutto il resto — parsing, verifica del CaseContext,
retrieval, gate, status, dossier — viene **eseguito**, non rigiocato.

Non sono mock. Sono le risposte reali del modello registrate al commit
``6ee64c5``, con transport, quote, ``source_unit_id``, prompt version, token e
latenza. Ogni stage rigiocato è marcato ``replayed: true``: presentare un replay
come esecuzione sarebbe la sola cosa peggiore che non poterlo eseguire.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from backend.research_pipeline import data_access as da

REPLAY_NOTE = "artefatto congelato del pilot 6ee64c5: risposta reale del modello, non rieseguita ora"


@lru_cache(maxsize=1)
def _enricher_runs_by_key() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (row["case_id"], row["paper_id"]): row
        for row in da.load_frozen_enricher_runs()
    }


@lru_cache(maxsize=1)
def _validations_by_key() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (row["case_id"], row["paper_id"]): row
        for row in da.read_jsonl(da.frozen_validation_results_path())
    }


@lru_cache(maxsize=1)
def _selection_by_case() -> dict[str, list[dict[str, Any]]]:
    # Il file raggruppa per caso: ``{"case_id": ..., "selections": [...]}``, con
    # una selezione per candidate. Appiattire qui evita di propagare la forma
    # dell'artefatto nel resto del codice.
    return {
        row["case_id"]: list(row.get("selections") or [])
        for row in da.read_jsonl(da.frozen_paper_selection_path())
    }


@lru_cache(maxsize=1)
def _parser_outputs_by_case() -> dict[str, dict[str, Any]]:
    path = da.data_root() / "benchmarks/mtb_evidence/end_to_end_pipeline_pilot/casecontext_outputs.jsonl"
    return {row["case_id"]: row for row in da.read_jsonl(path)}


def has_frozen_case(case_id: str) -> bool:
    return case_id in _parser_outputs_by_case()


def frozen_case_ids() -> tuple[str, ...]:
    return tuple(sorted(_parser_outputs_by_case()))


def parser_fn(budget: Any, case_id: str, clinical_text: str) -> dict[str, Any]:
    """Risposta del parser registrata per questo caso.

    Il budget non viene speso: nessuna chiamata di rete nuova avviene.
    """
    outputs = _parser_outputs_by_case()
    if case_id not in outputs:
        raise KeyError(
            f"nessun output del parser congelato per {case_id!r}: "
            "un caso inedito richiede una chiamata reale al modello"
        )
    return {**outputs[case_id], "replayed": True, "replay_note": REPLAY_NOTE}


def enricher_fn(
    budget: Any, case_id: str, candidate_id: str, paper_id: str, *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Chiamata all'enricher registrata per questa coppia caso/paper."""
    run = _enricher_runs_by_key().get((case_id, paper_id))
    if run is None:
        return {
            "transport_result": "V2_TRANSPORT_VALID", "enrichment": None,
            "case_id": case_id, "paper_id": paper_id, "candidate_id": candidate_id,
            "replayed": True, "replay_note": "nessuna chiamata registrata per questa coppia",
        }
    return {**run, "replayed": True, "replay_note": REPLAY_NOTE}


def selection_fn(association: dict[str, Any], source_units_by_id: dict[str, Any], *, case_id: str) -> dict[str, Any]:
    """Selezione dei paper registrata, filtrata sulla candidate corrente."""
    candidate_id = association["candidate"]["candidate_id"]
    for row in _selection_by_case().get(case_id, []):
        if row.get("candidate_id") == candidate_id:
            return {**row, "replayed": True, "replay_note": REPLAY_NOTE}
    return {
        "candidate_id": candidate_id, "selected_papers": [],
        "excluded_papers": [
            {"bundle_id": bundle["bundle_id"], "document_id": bundle["document_id"],
             "reason_codes": ["NO_FROZEN_SELECTION_FOR_CANDIDATE"]}
            for bundle in association.get("available_bundles", [])
        ],
        "replayed": True,
    }


def validation_fn(
    transport_result: str, enrichment: Any, *, case_id: str, paper_id: str, **kwargs: Any
) -> dict[str, Any]:
    """Esito di validazione registrato.

    La validazione **non** viene rieseguita: senza il testo delle SourceUnit ogni
    quote risulterebbe assente e verrebbe rigettata, producendo un
    ``REJECTED_QUOTE_NOT_FOUND`` che contraddirebbe l'esito reale del pilot.
    Rigiocare l'esito registrato è meno fuorviante che ricalcolarlo su dati
    incompleti.
    """
    row = _validations_by_key().get((case_id, paper_id))
    if row is None:
        return {"outcome": "ENRICHMENT_ABSTAINED",
                "reason_codes": ["NO_FROZEN_VALIDATION_FOR_PAPER"], "replayed": True}
    return {**row, "replayed": True, "replay_note": REPLAY_NOTE}


def summary() -> dict[str, Any]:
    """Sintesi degli artefatti disponibili, per la UI e per i test."""
    validations = list(_validations_by_key().values())
    outcomes: dict[str, int] = {}
    for row in validations:
        outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
    runs = list(_enricher_runs_by_key().values())
    return {
        "source_commit": "6ee64c5",
        "cases": list(frozen_case_ids()),
        "enricher_calls": len(runs),
        "quotes_proposed": sum(1 for r in runs if (r.get("enrichment") or {}).get("author_claim_quote")),
        "validation_outcomes": outcomes,
        "note": REPLAY_NOTE,
    }


# --- Narrativa congelata -----------------------------------------------------

def _narrative_path():
    return da.data_root() / "benchmarks/mtb_evidence/dossier_narrator/narrative_runs.jsonl"


@lru_cache(maxsize=1)
def _narratives_by_key() -> dict[tuple[str, str], dict[str, Any]]:
    """Narrative registrate, indicizzate per (case_id, narrator_input_hash).

    La chiave include l'hash della projection: una narrativa registrata per un
    dossier diverso non viene rigiocata al suo posto. Se il dossier cambia, la
    narrativa congelata smette di applicarsi ed e' corretto che sia cosi'.
    """
    path = _narrative_path()
    if not path.is_file():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["case_id"], r.get("narrator_input_hash", "")): r for r in rows}


def has_frozen_narrative(case_id: str, narrator_input_hash: str) -> bool:
    return (case_id, narrator_input_hash) in _narratives_by_key()


def narrator_fn(case_id: str, narrator_input: dict[str, Any], run_index: int = 0) -> dict[str, Any]:
    """Narrativa registrata per questo dossier, o assenza dichiarata.

    Non inventa nulla: se non esiste una narrativa congelata per questa esatta
    projection, restituisce ``narrative=None`` e la pipeline usa il fallback
    strutturato. Non e' un errore: e' l'assenza dichiarata.
    """
    key = (case_id, narrator_input.get("narrator_input_hash", ""))
    row = _narratives_by_key().get(key)
    if row is None:
        return {"case_id": case_id, "transport_result": "NO_FROZEN_NARRATIVE",
                "transport_reason_codes": ["NO_FROZEN_NARRATIVE_FOR_THIS_DOSSIER"],
                "narrative": None, "replayed": True,
                "narrator_input_hash": key[1], "replay_note": REPLAY_NOTE}
    return {**row, "replayed": True, "replay_note": REPLAY_NOTE}
