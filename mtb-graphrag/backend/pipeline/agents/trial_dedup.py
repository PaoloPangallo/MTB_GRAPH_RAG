"""Deduplicazione dei trial clinici per NCT ID.

Funzione pura, senza dipendenze da LLM/Neo4j: resta testabile in isolamento
anche quando l'ambiente non ha i pacchetti opzionali del resto della
pipeline (es. ``langchain-ollama``) installati.
"""

from __future__ import annotations


def deduplicate_trials(records: list[dict]) -> list[dict]:
    """Deduplica per NCT ID: ``OPTIONAL MATCH ... TESTS_DRUG`` nella query
    Cypher produce una riga per ogni farmaco corrispondente dello stesso
    trial, quindi lo stesso NCT ID può comparire più volte nel risultato
    grezzo. Qui le righe con lo stesso NCT ID vengono unite in un solo
    record, unendo i farmaci testati invece di perdere informazione o
    mostrare il trial duplicato."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    passthrough: list[dict] = []
    for record in records:
        nct_id = record.get("nct_id")
        if not nct_id:
            passthrough.append(record)
            continue
        if nct_id not in merged:
            merged[nct_id] = dict(record)
            order.append(nct_id)
            continue
        existing_drug = merged[nct_id].get("drug_tested")
        new_drug = record.get("drug_tested")
        if new_drug and new_drug != existing_drug:
            combined = {drug for drug in (existing_drug, new_drug) if drug}
            merged[nct_id]["drug_tested"] = ", ".join(sorted(combined))
    return [merged[nct_id] for nct_id in order] + passthrough
