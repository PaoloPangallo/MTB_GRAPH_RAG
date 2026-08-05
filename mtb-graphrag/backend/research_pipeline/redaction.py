"""Redazione dei record prima che raggiungano ledger, API o disco.

Promosso da ``run_pilot.py`` del pilot, dove viveva come helper privato del
runner. Non è un dettaglio del runner: è una funzione di sicurezza, e va
applicata su **ogni** percorso che espone una candidate — evento, risposta API,
artefatto su disco — non solo su quello che il runner usava.

Il campo critico è ``GraphCandidateAssertion.source_properties``, che trasporta
evidence statement curati in testo libero (centinaia di caratteri) copiati dal
repository delle candidate. Nessuna logica della pipeline lo legge: si usano
solo ``candidate_id``, ``disease``, ``biomarkers``, ``interventions``,
``direction`` e ``predicate``. Trasportarlo significherebbe pubblicare testo di
terzi senza motivo.
"""

from __future__ import annotations

from typing import Any, Mapping

#: Chiavi rimosse da ogni candidate prima dell'esposizione. Nessuna è letta
#: dalla pipeline: rimuoverle non degrada alcun risultato.
_DROPPED_CANDIDATE_KEYS: frozenset[str] = frozenset({"source_properties"})


def redact_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Candidate senza i campi di testo libero non necessari."""
    return {key: value for key, value in candidate.items() if key not in _DROPPED_CANDIDATE_KEYS}


def redact_retrieval_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Esito di retrieval con ogni candidate redatta."""
    redacted = dict(result)
    redacted["associations"] = [
        {**association, "candidate": redact_candidate(association["candidate"])}
        for association in result.get("associations", [])
    ]
    return redacted


def candidate_carries_free_text(candidate: Mapping[str, Any]) -> bool:
    """Vero se la candidate contiene ancora campi da redigere.

    Serve come asserzione nei test e come guardia prima della scrittura: è più
    utile fallire che scoprire il testo in un archivio append-only.
    """
    return bool(_DROPPED_CANDIDATE_KEYS & set(candidate))
