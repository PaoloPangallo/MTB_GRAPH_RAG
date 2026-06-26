"""
ablation_enricher.py — Condizione 3: Standalone OncoKB Enricher.

Esegue la chiamata diretta alle API di OncoKB bypassando completamente Neo4j e gli altri agenti.
Genera il report compilando i dati tramite lo scaffold di prompt standard.

v2 — Fix per confronto fair:
  - Tumor type aliases (OncoKB usa nomi interni diversi dal benchmark)
  - Fallback a "Oncogenic Mutations" per notazioni variante generiche
  - Fusion parser corretto (estrae entrambi i geni; self-fusion per gene singolo)
  - Biomarker tumor-agnostic (MSI-H / TMB-H, nessun tumorType)
"""

from __future__ import annotations

import json
import re
from langchain_core.messages import SystemMessage, HumanMessage

from backend.pipeline.llm import llm
from backend.pipeline.state import MTBState
from backend.pipeline.agents.oncokb_enricher import _oncokb_request
from backend.pipeline.agents.synthesizer import SYNTHESIZER_SYSTEM
from backend.pipeline.mappings import KB_TO_ONCOKB

# ──────────────────────────────────────────────────────────────────────────
# Dizionario di alias: nome tumor nel benchmark → nome interno di OncoKB
# Motivazione empirica: verificato con test diretti sulle API (2025-06-23)
# ──────────────────────────────────────────────────────────────────────────
ONCOKB_TUMOR_ALIASES: dict[str, str] = {
    "Chronic Myeloid Leukemia": "CML",
    "Gastric Cancer":           "Esophagogastric Adenocarcinoma",
    "Gastric Adenocarcinoma":   "Esophagogastric Adenocarcinoma",
}

# Notazioni variante generiche che non mappano a un singolo trattamento OncoKB
# ma per cui esiste un termine canonico: "Oncogenic Mutations"
_GENERIC_TERMS = {
    "Mutation", "Deletion", "Amplification", "Insertion",
    "Overexpression", "any", "Loss",
}


def _is_generic_alteration(variant: str) -> bool:
    """True se la variante è troppo generica per una query esatta OncoKB.

    Sono generiche:
    - Termini singoli come "Mutation", "Deletion" ecc.
    - Notazioni a livello di esone ("Exon XX ...")
    - Notazioni proteiche incomplete tipo "R132" (lettera + solo cifre, senza AA sostitutiva)
    """
    v = variant.strip()
    if v in _GENERIC_TERMS:
        return True
    if v.lower().startswith("exon "):
        return True
    # Protein change incompleto: "R132", "G12" — completo sarebbe "R132H", "G12C"
    if re.match(r'^[A-Z]\d+$', v):
        return True
    return False


def _extract_level1_2(data: dict | None) -> list[dict]:
    """Estrae i trattamenti LEVEL_1 e LEVEL_2 dalla risposta OncoKB."""
    if not data or "treatments" not in data:
        return []
    result = []
    for t in data.get("treatments", []):
        if t.get("level") not in ("LEVEL_1", "LEVEL_2"):
            continue
        result.append({
            "drugs":       [d["drugName"] for d in t.get("drugs", [])],
            "level":       t.get("level"),
            "fda_level":   t.get("fdaLevel"),
            "cancer_type": t.get("levelAssociatedCancerType", {}).get("name", ""),
            "pmids":       t.get("pmids", []),
            "description": t.get("description", "")[:400],
        })
    return result


def _build_fair_oncokb_params(
    gene: str,
    variant: str,
    tumor_type: str,
    alteration_type: str,
) -> tuple[str, dict]:
    """Costruisce (endpoint, params) con gestione corretta dei casi limite.

    Rispetto alla versione originale (_build_oncokb_params in oncokb_enricher.py):
    - Applica ONCOKB_TUMOR_ALIASES per correggere nomi tumor non riconosciuti
    - Per biomarker (MSI/TMB): usa MSI-H/TMB-H e rimuove tumorType (tumor-agnostic)
    - Per fusion con gene singolo: tenta di estrarre entrambi i geni dal variant;
      se non possibile, usa self-fusion (A=gene, B=gene) per ottenere evidenze gene-level
    - Per fusion tumor-agnostic: rimuove tumorType se il tumor type è "Solid Tumor"
    """
    tumor_oncokb = ONCOKB_TUMOR_ALIASES.get(tumor_type, tumor_type)

    if alteration_type == "biomarker":
        # MSI-High → MSI-H, TMB-High → TMB-H (formato atteso da OncoKB)
        oncokb_alt = KB_TO_ONCOKB.get(variant, variant)
        oncokb_alt = oncokb_alt.replace("-High", "-H").replace("-high", "-H")
        # I biomarker sono tumor-agnostic in OncoKB → no tumorType
        return "mutations/byProteinChange", {"alteration": oncokb_alt}

    elif alteration_type == "fusion":
        if "-" in gene:
            # Gene già nel formato "GENEА-GENEB" (es. EML4-ALK)
            parts = gene.split("-", 1)
            gene_a, gene_b = parts[0].strip(), parts[1].strip()
        else:
            # Gene singolo: prova a estrarre il partner dal campo variant
            # es. variant="BCR-ABL1 Fusion" → gene_a=BCR, gene_b=ABL1
            fusion_str = re.sub(r'\b[Ff]usion\b', '', variant).strip(" -")
            if "-" in fusion_str:
                parts = [p.strip() for p in fusion_str.split("-", 1)]
                gene_a, gene_b = parts[0], parts[1]
            else:
                # Partner sconosciuto: self-fusion cattura le evidenze gene-level
                gene_a, gene_b = gene, gene

        params: dict = {
            "hugoSymbolA":           gene_a,
            "hugoSymbolB":           gene_b,
            "structuralVariantType": "FUSION",
            "isFunctionalFusion":    "true",
        }
        # Ometti tumorType per fusions tumor-agnostiche
        # ("Solid Tumor" non è un tipo riconosciuto da OncoKB)
        if tumor_oncokb and tumor_oncokb not in ("Solid Tumor", "All Tumors", ""):
            params["tumorType"] = tumor_oncokb
        return "structuralVariants", params

    elif alteration_type == "cna":
        cna_type = "AMPLIFICATION" if "amplif" in variant.lower() else "DELETION"
        return "copyNumberAlterations", {
            "hugoSymbol":             gene,
            "copyNameAlterationType": cna_type,
            "tumorType":              tumor_oncokb,
        }

    else:
        # point_mutation, itd, atypical
        alteration = "ITD" if alteration_type == "itd" else variant
        return "mutations/byProteinChange", {
            "hugoSymbol": gene,
            "alteration": alteration,
            "tumorType":  tumor_oncokb,
        }


def run_enricher_only(
    gene: str,
    variant: str,
    tumor_type: str,
    alteration_type: str,
    therapy_line: str,
) -> str:
    """Esegue la chiamata API a OncoKB, estrae i trattamenti LEVEL_1/2 e genera il report.

    Strategia multi-step:
    1. Query primaria con il formato corretto per il tipo di alterazione
    2. Se 0 trattamenti e variante è generica → fallback con "Oncogenic Mutations"
    3. Report generato tramite LLM con il prompt standard (identico a tutte le altre condizioni)
    """
    # ── Step 1: Query primaria ─────────────────────────────────────────
    endpoint, params = _build_fair_oncokb_params(gene, variant, tumor_type, alteration_type)
    print(f"  [OncoKB] Query primaria: {endpoint} | params={params}")
    data = _oncokb_request(endpoint, params)
    new_treatments = _extract_level1_2(data)
    print(f"  [OncoKB] Trattamenti LEVEL_1/2: {len(new_treatments)}")

    # ── Step 2: Fallback con "Oncogenic Mutations" ─────────────────────
    # Si attiva solo per point_mutation/atypical con variante generica
    if not new_treatments and alteration_type in ("point_mutation", "atypical") and gene:
        if _is_generic_alteration(variant):
            tumor_oncokb = ONCOKB_TUMOR_ALIASES.get(tumor_type, tumor_type)
            fb_params = {
                "hugoSymbol": gene,
                "alteration": "Oncogenic Mutations",
                "tumorType":  tumor_oncokb,
            }
            print(f"  [OncoKB Fallback] Variante generica '{variant}' → retry con 'Oncogenic Mutations'")
            fb_data = _oncokb_request("mutations/byProteinChange", fb_params)
            fb_treatments = _extract_level1_2(fb_data)
            if fb_treatments:
                print(f"  [OncoKB Fallback] Trovati {len(fb_treatments)} trattamenti.")
                new_treatments = fb_treatments

    # ── Step 3: Costruzione contesto testuale ──────────────────────────
    ctx = [
        f"=== VARIANTE ===\n"
        f"Gene: {gene} | Variante: {variant} | "
        f"Tipo: {alteration_type} | Tumore: {tumor_type} | "
        f"Linea: {therapy_line}\n"
    ]

    if new_treatments:
        formatted_treatments = []
        for t in new_treatments:
            drugs_str = " + ".join(t["drugs"])
            pmids_str = ", ".join(str(p) for p in t["pmids"])
            formatted_treatments.append(
                f"- Farmaco: {drugs_str} (Livello: {t['level']} | FDA Level: {t['fda_level']})\n"
                f"  Tumore: {t['cancer_type']} | PMID di supporto: {pmids_str}\n"
                f"  Descrizione: {t['description']}"
            )
        ctx.append("=== EVIDENZE ONCOKB (LEVEL_1/2) ===\n" + "\n\n".join(formatted_treatments))
    else:
        ctx.append(
            "=== EVIDENZE ONCOKB (LEVEL_1/2) ===\n"
            "Nessun trattamento o evidenza di livello 1 o 2 rilevato in OncoKB per questa alterazione."
        )

    # PMID verificati (per compatibilità con SYNTHESIZER_SYSTEM)
    all_pmids: set[str] = set()
    for t in new_treatments:
        all_pmids.update(str(p) for p in t["pmids"])

    if all_pmids:
        ctx.append(
            "=== PMID VERIFICATI NEL KNOWLEDGE GRAPH ===\n"
            + "\n".join(f"- {pmid}: Evidenza da OncoKB API" for pmid in sorted(all_pmids))
        )
    else:
        ctx.append("=== PMID VERIFICATI NEL KNOWLEDGE GRAPH ===\n(nessuno verificato)")

    ctx.append(
        "=== NOTA ===\nUsa le sole evidenze fornite sopra da OncoKB. "
        "Non aggiungere altri dati non menzionati nel contesto. "
        "Assicurati di riportare le citazioni inline [PMID: XXXXXX]."
    )

    # ── Step 4: Generazione report via LLM ────────────────────────────
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content="\n\n".join(ctx))
    ])

    return response.content
