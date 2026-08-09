"""Etichette storiche di esecuzione e origine degli artefatti.

**Questo modulo non decide più alcun instradamento.** Esiste un solo runtime
operativo — quello canonico — e nessun campo di questo modulo può cambiarlo.
Ciò che resta qui è vocabolario di *lettura*: serve a decodificare run già
registrate sul ledger e a etichettare gli artefatti di ricerca, non a scegliere
quale percorso eseguire.

Il vocabolario continua a rendere impossibile una sola cosa: che un artefatto
registrato in una run precedente venga presentato come appena prodotto.

Due assi **distinti**, che il runtime precedente confondeva in un unico campo
booleano ``replayed``:

``execution_mode``
    Etichetta della run. Il runtime canonico scrive sempre ``CANONICAL_MODE``.
    ``REPLAY`` compare soltanto nelle run prodotte da harness di regressione e
    nelle run storiche già sul ledger; ``HYBRID`` resta un esito constatabile.

``artifact_origin``
    Da dove viene il risultato di *questo* stage. Un documento letto da cache
    locale è ``DETERMINISTIC_CACHE`` e resta parte di una run canonica; una
    risposta del modello registrata al commit ``6ee64c5`` è ``RECORDED_REAL_RUN``
    e non lo è. Chiamare "cached" entrambe le cose è precisamente l'errore che
    questo modulo impedisce.

La regola di classificazione della run è deliberatamente asimmetrica: un solo
artefatto registrato declassa la run da ``LIVE`` a ``HYBRID``, mentre nessuna
combinazione di stage può promuovere a ``LIVE`` una run avviata in ``REPLAY``.
Il declassamento è automatico e non disattivabile. Nel runtime canonico
``RECORDED_REAL_RUN`` è irraggiungibile per costruzione, quindi
``HYBRID`` non è più producibile: la regola resta per decodificare lo storico.
"""

from __future__ import annotations

from typing import Any, Iterable

# --- Etichette storiche (metadata, NON autorità di routing) ------------------

LIVE = "LIVE"
REPLAY = "REPLAY"
HYBRID = "HYBRID"

EXECUTION_MODES: tuple[str, ...] = (LIVE, REPLAY, HYBRID)

#: Etichetta scritta da ogni run del runtime canonico.
#:
#: Vale ``"LIVE"`` di proposito, e non una stringa nuova: il valore viaggia nei
#: payload del ledger, negli scorecard di valutazione già prodotti e nella
#: decodifica delle run storiche. Cambiarlo renderebbe illeggibile tutto ciò che
#: è stato registrato prima, in cambio di nulla — il nome del percorso nella
#: tesi e nel diagramma non dipende da questa costante.
#:
#: ``legacy_internal_name = "LIVE"`` · ``thesis_presentation_name = "CANONICAL RUNTIME"``.
CANONICAL_MODE = LIVE

#: Etichetta usata dagli harness di ricerca e regressione quando rigiocano
#: artefatti congelati. Non è richiedibile e non è raggiungibile dall'API.
RESEARCH_FROZEN_MODE = REPLAY

#: Una sola modalità è richiedibile, ed è quella canonica. ``REPLAY`` è uscito
#: dall'insieme: non è più una scelta del chiamante ma un'etichetta di artefatti
#: di ricerca. ``HYBRID`` non è mai stato richiedibile — è un esito che si
#: constata, e ammetterlo come input darebbe un modo di dichiarare in partenza
#: una run mista senza che nessuno stage lo giustifichi.
REQUESTABLE_MODES: tuple[str, ...] = (CANONICAL_MODE,)

# --- Origine degli artefatti ------------------------------------------------

GENERATED_NOW = "GENERATED_NOW"
RECORDED_REAL_RUN = "RECORDED_REAL_RUN"
DETERMINISTIC_CACHE = "DETERMINISTIC_CACHE"
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_EXECUTED = "NOT_EXECUTED"

ARTIFACT_ORIGINS: tuple[str, ...] = (
    GENERATED_NOW, RECORDED_REAL_RUN, DETERMINISTIC_CACHE,
    NOT_APPLICABLE, NOT_EXECUTED,
)

#: Le sole origini che contano come "artefatto rigiocato". ``DETERMINISTIC_CACHE``
#: è escluso apposta: leggere un documento dalla cache autorizzata è lettura di
#: una fonte, non riproduzione di un output.
REPLAYED_ORIGINS: frozenset[str] = frozenset({RECORDED_REAL_RUN})


class UnknownExecutionMode(ValueError):
    """Modalità non riconosciuta. Non esiste un default sicuro."""


def normalize_requested_mode(value: Any) -> str:
    """Valida un'etichetta di modalità. Esiste un solo valore ammesso.

    Resta come guardia di vocabolario, non come selettore: nessun percorso
    dell'API la usa più per scegliere cosa eseguire. Serve a impedire che un
    chiamante interno reintroduca per distrazione una modalità dedotta.

    L'assenza di un default è intenzionale: il runtime precedente sceglieva la
    modalità osservando se esistessero artefatti congelati per il caso, e quella
    deduzione è esattamente il fallback silenzioso rimosso.
    """
    if not isinstance(value, str):
        raise UnknownExecutionMode(
            f"execution_mode assente o non testuale: {value!r}. "
            f"Valori ammessi: {list(REQUESTABLE_MODES)}"
        )
    mode = value.strip().upper()
    if mode == HYBRID:
        raise UnknownExecutionMode(
            "HYBRID non è richiedibile: è la classificazione di una run che ha "
            "usato artefatti registrati pur essendo stata avviata nel runtime canonico"
        )
    if mode == REPLAY:
        raise UnknownExecutionMode(
            "REPLAY non è più una modalità di esecuzione richiedibile: il replay "
            "degli artefatti congelati è infrastruttura di ricerca e regressione, "
            "raggiungibile solo iniettando gli adattatori in "
            "``orchestrator.run_case(research_frozen_artifacts=True, ...)``"
        )
    if mode not in REQUESTABLE_MODES:
        raise UnknownExecutionMode(
            f"execution_mode sconosciuto: {value!r}. "
            f"Valori ammessi: {list(REQUESTABLE_MODES)}"
        )
    return mode


def assert_origin(origin: str) -> str:
    if origin not in ARTIFACT_ORIGINS:
        raise ValueError(f"artifact_origin sconosciuto: {origin!r}")
    return origin


def count_replay_artifacts(origins: Iterable[str]) -> int:
    """Quanti stage hanno usato un artefatto registrato."""
    return sum(1 for origin in origins if origin in REPLAYED_ORIGINS)


def classify_run_mode(requested: str, origins: Iterable[str]) -> str:
    """Modalità **effettiva** della run, dalle origini dei suoi stage.

    Una run avviata in LIVE che abbia usato anche un solo artefatto registrato è
    ``HYBRID``. Non è una sfumatura: è la differenza fra una dimostrazione e una
    ricostruzione, e deve essere leggibile senza aprire i singoli stage.
    """
    if requested == REPLAY:
        return REPLAY
    return HYBRID if count_replay_artifacts(origins) > 0 else LIVE


def is_fully_live(requested: str, origins: Iterable[str]) -> bool:
    """Vero solo per una run LIVE con zero artefatti registrati."""
    return classify_run_mode(requested, origins) == LIVE and requested == LIVE


def origin_for_replay(stage_executed: bool = True) -> str:
    return RECORDED_REAL_RUN if stage_executed else NOT_EXECUTED


def summarize(requested: str, origins: Iterable[str]) -> dict[str, Any]:
    """Intestazione di run per la UI. Calcolata qui, mai nel frontend."""
    materialized = list(origins)
    effective = classify_run_mode(requested, materialized)
    replay_used = count_replay_artifacts(materialized)
    return {
        "requested_mode": requested,
        "execution_mode": effective,
        "fully_live": effective == LIVE and requested == LIVE,
        "replay_artifacts_used": replay_used,
        "origin_counts": {
            origin: sum(1 for value in materialized if value == origin)
            for origin in ARTIFACT_ORIGINS
            if any(value == origin for value in materialized)
        },
    }
