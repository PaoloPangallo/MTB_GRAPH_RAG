"""Rappresentazione conservativa dei regimi terapeutici.

L'audit ha stabilito che il ``COMPLETE_KG_CSV_EXPORT`` **non contiene** alcun
campo che descriva la relazione fra i farmaci di uno stesso record Evidence:
``edge_targets_drug.csv`` ha cinque colonne
(``source_evidence_id``, ``target_drug_concept_id``, ``evidence_level``,
``significance``, ``evidence_direction``) e gli archi fratelli non differiscono
in nulla oltre al farmaco.

Conseguenza vincolante: per un record con più farmaci **non è possibile**
stabilire se si tratti di una combinazione, di alternative confrontate o di una
sequenza. La rappresentazione corretta non è ricostruire il regime, ma smettere
di affermare implicitamente che ogni farmaco porta individualmente la direzione
del record.

Ciò che questo modulo **non** fa, per divieto esplicito:

* non deduce la struttura dal numero di farmaci;
* non usa il PMID né il titolo del paper come fonte nascosta;
* non interpreta ``/``, ``+`` o ``&`` nei nomi dei farmaci — appartengono al
  nome proprio del prodotto (``SULFAMETHOXAZOLE / TRIMETHOPRIM``);
* non assegna ruoli farmacologici assenti dall'export;
* non sceglie un farmaco principale.
"""

from __future__ import annotations

import hashlib
from typing import Any

# intervention_structure
SINGLE_AGENT = "SINGLE_AGENT"
COMBINATION_CONFIRMED = "COMBINATION_CONFIRMED"
ALTERNATIVE_CONFIRMED = "ALTERNATIVE_CONFIRMED"
SEQUENTIAL_CONFIRMED = "SEQUENTIAL_CONFIRMED"
MULTI_COMPONENT_UNRESOLVED = "MULTI_COMPONENT_UNRESOLVED"
STRUCTURE_UNKNOWN = "UNKNOWN"

# regimen_semantics_status
SEMANTICS_PRESERVED = "SEMANTICS_PRESERVED"
SEMANTICS_PARTIALLY_PRESERVED = "SEMANTICS_PARTIALLY_PRESERVED"
SEMANTICS_UNAVAILABLE_IN_SOURCE = "SEMANTICS_UNAVAILABLE_IN_SOURCE"
SEMANTICS_AMBIGUOUS = "SEMANTICS_AMBIGUOUS"
NOT_APPLICABLE = "NOT_APPLICABLE"

# component_role — assegnato solo se l'export lo contiene, cosa che qui non
# accade mai. `UNKNOWN` è quindi l'unico valore prodotto su questa sorgente.
ROLE_UNKNOWN = "UNKNOWN"

#: Codice registrato sulle candidate il cui regime non è ricostruibile.
REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT = "REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT"


def regimen_id(evidence_id: str, component_ids: list[str]) -> str:
    """Identificatore stabile dell'unità terapeutica.

    Deterministico e indipendente dall'ordine di riga dei componenti, perché
    l'ordine nell'export non è informativo.
    """
    payload = f"{evidence_id}|" + "|".join(sorted(component_ids))
    return f"RGM-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def build_intervention(
    evidence_id: str,
    drug_rows: list[dict[str, Any]],
    drug_nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Rappresentazione dell'intervento a partire dagli archi verso farmaco.

    ``drug_rows`` sono **tutti** gli archi del medesimo record Evidence: la
    decisione è presa a livello di record, non di singolo arco.
    """
    components = []
    for row in drug_rows:
        concept_id = str(row.get("target_drug_concept_id") or "").strip()
        node = drug_nodes.get(concept_id) or {}
        components.append({
            "concept_id": concept_id,
            "name": (node.get("drug_name") or concept_id) or None,
            "node_id": f"Drug:{concept_id}",
            "component_role": ROLE_UNKNOWN,
        })

    component_ids = [c["concept_id"] for c in components]
    raw = " | ".join(c["name"] or c["concept_id"] for c in components)

    if len(components) == 0:
        return {
            "intervention_expression_raw": None,
            "intervention_components": [],
            "intervention_structure": STRUCTURE_UNKNOWN,
            "regimen_semantics_status": NOT_APPLICABLE,
            "regimen_id": None,
            "regimen_limitations": [],
        }

    if len(components) == 1:
        return {
            "intervention_expression_raw": components[0]["name"],
            "intervention_components": components,
            "intervention_structure": SINGLE_AGENT,
            "regimen_semantics_status": NOT_APPLICABLE,
            "regimen_id": regimen_id(evidence_id, component_ids),
            "regimen_limitations": [],
        }

    # Più farmaci: la sorgente non consente di stabilirne la relazione.
    return {
        "intervention_expression_raw": raw,
        "intervention_components": components,
        "intervention_structure": MULTI_COMPONENT_UNRESOLVED,
        "regimen_semantics_status": SEMANTICS_UNAVAILABLE_IN_SOURCE,
        "regimen_id": regimen_id(evidence_id, component_ids),
        "regimen_limitations": [REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT],
    }


def eligible_for_intervention_exact_match(intervention: dict[str, Any]) -> bool:
    """Un regime irrisolto non è eleggibile al match esatto sull'intervento.

    Non perché i componenti siano ignoti — sono tutti conservati — ma perché
    non è noto se il paziente debba riceverli insieme o in alternativa.
    """
    return intervention.get("intervention_structure") in {
        SINGLE_AGENT, COMBINATION_CONFIRMED, ALTERNATIVE_CONFIRMED, SEQUENTIAL_CONFIRMED,
    }
