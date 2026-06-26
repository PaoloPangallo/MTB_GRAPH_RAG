"""
OncoKB Enricher — Nodo opzionale (human-in-the-loop).
Si attiva solo se enrich_with_oncokb=True.
Endpoint diverso per alteration_type.
"""

from __future__ import annotations

import json
import requests
from langchain_core.messages import HumanMessage, SystemMessage

from backend.pipeline.state import MTBState
from backend.pipeline.llm import ONCOKB_TOKEN, llm
from backend.pipeline.mappings import KB_TO_ONCOKB

INTEGRATOR_SYSTEM = """Sei un oncologo clinico esperto per il Molecular Tumor Board.
Ti viene fornito un report MTB di base e una lista di nuovi trattamenti/evidenze estratti in tempo reale da OncoKB.
Il tuo compito è integrare in modo scientifico ed elegante i dati OncoKB all'interno del report di base.

Regole di integrazione:
1. Nella Sezione 1 (Variante e ESCAT), se OncoKB riporta un livello di evidenza superiore o indica che la variante ha un significato terapeutico live, aggiorna la classificazione citando esplicitamente OncoKB.
2. Nella Sezione 2 (Terapia raccomandata), inserisci i nuovi farmaci raccomandati da OncoKB (con i relativi companion diagnostic CDx se indicati) specificando il livello di evidenza OncoKB (es. LEVEL_1, LEVEL_2) e inserendo inline i PMID forniti nel JSON [PMID: XXXXX].
3. Se un farmaco precedentemente raccomandato nel report base è in realtà non corretto o controindicato alla luce delle evidenze (es. Cetuximab/Panitumumab da soli per KRAS G12C in CRC senza inibitore di KRAS), rimuovilo o correggilo.
4. Nella Sezione 5 (PMID verificati), elenca anche i nuovi PMID provenienti da OncoKB.

Ritorna esclusivamente il report finale arricchito in formato Markdown, mantenendo la struttura in italiano e lo stile clinico formale.
"""



ONCOKB_BASE = "https://www.oncokb.org/api/v1/annotate"


def _oncokb_request(endpoint: str, params: dict) -> dict | None:
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {ONCOKB_TOKEN}",
    }
    try:
        r = requests.get(f"{ONCOKB_BASE}/{endpoint}", params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[OncoKB Enricher] Errore chiamata API: {e}")
        return None


def _build_oncokb_params(state: MTBState) -> tuple[str, dict]:
    """Restituisce (endpoint, params) in base ad alteration_type."""
    alt_type   = state["alteration_type"]
    gene       = state.get("gene") or ""
    variant    = state["variant"]
    tumor_type = state["tumor_type"]

    if alt_type in ("point_mutation", "itd", "atypical"):
        alteration = "ITD" if alt_type == "itd" else variant
        return "mutations/byProteinChange", {
            "hugoSymbol": gene,
            "alteration": alteration,
            "tumorType":  tumor_type,
        }

    elif alt_type == "fusion":
        # Es. "EML4-ALK Fusion" → hugoSymbolA=EML4, hugoSymbolB=ALK
        parts = gene.split("-") if "-" in gene else [gene, ""]
        return "structuralVariants", {
            "hugoSymbolA":          parts[0],
            "hugoSymbolB":          parts[1] if len(parts) > 1 else gene,
            "structuralVariantType": "FUSION",
            "isFunctionalFusion":    "true",
            "tumorType":             tumor_type,
        }

    elif alt_type == "cna":
        cna_type = "AMPLIFICATION" if "amplif" in variant.lower() else "DELETION"
        return "copyNumberAlterations", {
            "hugoSymbol":            gene,
            "copyNameAlterationType": cna_type,
            "tumorType":             tumor_type,
        }

    elif alt_type == "biomarker":
        # MSI-High o TMB-High — nessun gene richiesto
        oncokb_alt = KB_TO_ONCOKB.get(variant, variant)
        return "mutations/byProteinChange", {
            "alteration": oncokb_alt,
            "tumorType":  tumor_type,
        }

    return "mutations/byProteinChange", {
        "hugoSymbol": gene,
        "alteration": variant,
        "tumorType":  tumor_type,
    }


def oncokb_enricher(state: MTBState) -> MTBState:
    """Nodo opzionale — si attiva solo se enrich_with_oncokb=True."""
    if not state.get("enrich_with_oncokb"):
        return {**state, "oncokb_enrichment": []}

    endpoint, params = _build_oncokb_params(state)
    data = _oncokb_request(endpoint, params)

    if not data or "treatments" not in data:
        return {**state, "oncokb_enrichment": []}

    # Farmaci già nel report base
    existing_drugs = {r["drug_name"].upper() for r in state.get("drug_candidates", [])}

    # Filtra LEVEL_1 e LEVEL_2 non già presenti nel report
    new_treatments = []
    for t in data.get("treatments", []):
        if t.get("level") not in ("LEVEL_1", "LEVEL_2"):
            continue
        drug_names = [d["drugName"].upper() for d in t.get("drugs", [])]
        if all(d in existing_drugs for d in drug_names):
            continue  # già nel report base
        new_treatments.append({
            "drugs":       [d["drugName"] for d in t.get("drugs", [])],
            "level":       t.get("level"),
            "fda_level":   t.get("fdaLevel"),
            "cancer_type": t.get("levelAssociatedCancerType", {}).get("name", ""),
            "pmids":       t.get("pmids", []),
            "description": t.get("description", "")[:400],
        })

    # Integrazione clinica se ci sono nuovi trattamenti e un report base esistente
    report = state.get("report") or ""
    if new_treatments and report:
        try:
            integration_msg = (
                f"Report Base:\n{report}\n\n"
                f"Dati di Arricchimento OncoKB (LEVEL_1/2):\n{json.dumps(new_treatments, indent=2, ensure_ascii=False)}"
            )
            response = llm.invoke([
                SystemMessage(content=INTEGRATOR_SYSTEM),
                HumanMessage(content=integration_msg),
            ])
            report = response.content
        except Exception as e:
            print(f"[OncoKB Enricher] Errore integrazione LLM: {e}")

    return {**state, "oncokb_enrichment": new_treatments, "report": report}
