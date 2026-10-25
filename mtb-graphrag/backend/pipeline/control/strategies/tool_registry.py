"""Registry degli strumenti KG autorizzati, comune alle due architetture.

Entrambe le strategie di raccolta attingono a questo registry: l'allow-list è
la stessa, cambia soltanto *chi* decide l'ordine. Se le due architetture
usassero registry diversi, il confronto misurerebbe la disponibilità degli
strumenti anziché l'orchestrazione.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

Tool = Callable[[dict[str, Any]], dict[str, Any]]

#: Versione dichiarata di ogni strumento, registrata nel ledger insieme alla
#: chiamata. Serve a distinguere un risultato prodotto da una logica di
#: retrieval diversa: senza, due run con lo stesso tool_path non sono
#: confrontabili se il codice dello strumento è cambiato nel frattempo.
TOOL_VERSIONS: Mapping[str, str] = {
    "assess_complexity": "1.0",
    "interpret_variant": "1.0",
    "identify_targets": "1.0",
    "match_trials": "1.1",  # dedup per NCT ID
    "check_resistance": "1.1",  # fallback gene-level filtrato
    "enrich_oncokb": "1.0",
}

#: Chiave dello stato in cui ogni strumento deposita i propri record, con il
#: tipo di record corrispondente. È ciò che permette al replay di instradare i
#: record senza cablare i nomi degli strumenti.
TOOL_OUTPUTS: Mapping[str, tuple[str, str]] = {
    "interpret_variant": ("evidence", "variant_data.evidence_records"),
    "identify_targets": ("drug", "drug_candidates"),
    "match_trials": ("trial", "trial_candidates"),
    "check_resistance": ("resistance", "resistance_data"),
    "enrich_oncokb": ("oncokb", "oncokb_enrichment"),
}

#: Strumenti che una riparazione di raccolta può richiamare. Esclude
#: ``assess_complexity`` (non contribuisce evidenza) e ``enrich_oncokb``
#: (arricchimento esterno opzionale, non un recupero di evidenza mancante).
REPAIRABLE_TOOLS = frozenset({
    "interpret_variant",
    "identify_targets",
    "match_trials",
    "check_resistance",
})


def tool_version(tool: str) -> str:
    return TOOL_VERSIONS.get(tool, "unknown")


def records_from_state(tool: str, state: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Estrae ``(record_kind, records)`` prodotti da uno strumento.

    Restituisce una lista vuota per gli strumenti che non producono record
    (``assess_complexity`` classifica soltanto): il replay li ignora senza
    doverli conoscere per nome.
    """
    mapping = TOOL_OUTPUTS.get(tool)
    if mapping is None:
        return "", []

    record_kind, path = mapping
    value: Any = state
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return record_kind, []
        value = value.get(part)

    if not isinstance(value, (list, tuple)):
        return record_kind, []
    return record_kind, [dict(item) for item in value if isinstance(item, Mapping)]
