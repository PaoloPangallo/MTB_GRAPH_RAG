"""
Synthesizer — Verifica PMID su nodi Publication via CITED_IN e genera il report MTB.
"""

from __future__ import annotations

import re
from langchain_core.messages import HumanMessage, SystemMessage

from backend.pipeline.state import MTBState
from backend.pipeline.llm import llm
from backend.pipeline.helpers import run_cypher
from backend.pipeline.cypher import CYPHER_VERIFY_PMIDS

# Identifica tutti i potenziali PMID (numeri da 7 a 8 cifre)
_PMID_LIKE_RE = re.compile(r'\b\d{7,8}\b')

def filtra_pmid_non_verificati(report_text: str, verified_pmids: set[int]) -> tuple[str, list[int]]:
    """
    Sostituisce nel testo ogni numero PMID-like (7-9 cifre) non presente nella lista verificata dal grafo.
    Restituisce (testo_filtrato, lista_pmid_rimossi).
    """
    rimossi: list[int] = []

    def sostituisci(match):
        num_str = match.group(0)
        num = int(num_str)
        if num in verified_pmids:
            return num_str
        else:
            rimossi.append(num)
            return "[PMID non verificato nel KG]"

    testo_filtrato = _PMID_LIKE_RE.sub(sostituisci, report_text)
    return testo_filtrato, rimossi


SYNTHESIZER_SYSTEM = """Sei un assistente clinico esperto per Molecular Tumor Board.
Produci un report strutturato e conciso in italiano.
IMPORTANTE:
- Collega ESPLICITAMENTE ogni singola raccomandazione terapeutica, ciascun livello ESCAT e ciascun meccanismo di resistenza al relativo PMID di supporto direttamente inline nel testo, MA SOLO se il PMID è realmente pertinente a quel farmaco (es. "Osimertinib è raccomandato come prima linea [PMID: 37937763]").
- ATTENZIONE: Non attribuire PMID a farmaci che non vi sono correlati nei paper di riferimento. Ad esempio, i PMID 39602630 e 39874977 si riferiscono esclusivamente allo studio CheckMate 8HW (Nivolumab + Ipilimumab) per il tumore del colon-retto MSI-H; non devi in alcun modo associarli a Pembrolizumab o Dostarlimab nel report.
- Se un farmaco non ha un PMID di supporto pertinente tra quelli verificati nel contesto, riporta la raccomandazione senza indicare alcun PMID (es. indicando il livello di evidenza nel database ma senza associare falsi riferimenti).
- Se un farmaco ha associata una companion diagnostic (CDx), riportala insieme al farmaco.
- Usa SOLO i PMID verificati forniti nel contesto dell'input. Non inventare citazioni esterne.

Struttura obbligatoria:
1. Variante e classificazione ESCAT (con citazioni inline [PMID: XXXXX] se pertinenti)
2. Terapia raccomandata (per ciascun farmaco e companion diagnostic, includere la spiegazione dell'evidenza clinica e la citazione inline [PMID: XXXXX] solo se pertinente)
3. Profilo di resistenza (descrivere le mutazioni di resistenza come T790M o C797S e come impattano le terapie, indicando esplicitamente i PMID di supporto inline [PMID: XXXXX])
4. Trial clinici eleggibili (se presenti nel contesto, con NCT ID)
5. Lista finale dei PMID verificati nel Knowledge Graph
"""


def synthesizer(state: MTBState) -> MTBState:
    raw_pmids: list[int] = []
    for r in state.get("variant_data", {}).get("evidence_records", []):
        if r.get("pmid"):
            raw_pmids.append(int(r["pmid"]))
    for r in state.get("resistance_data", []):
        if r.get("pmid"):
            raw_pmids.append(int(r["pmid"]))

    verified     = run_cypher(CYPHER_VERIFY_PMIDS, {"pmids": list(set(raw_pmids))})
    verified_map = {r["pmid"]: r["citation_text"] for r in verified}

    ctx = [
        f"=== VARIANTE ===\n"
        f"Gene: {state['gene']} | Variante: {state['variant']} | "
        f"Tipo: {state['alteration_type']} | Tumore: {state['tumor_type']} | "
        f"Linea: {state['therapy_line']}\nESCAT Tier: {state.get('escat_tier', 'N/D')}",

        "=== EVIDENZE CLINICHE (A/B) ===\n" + "\n".join(
            f"- {r['significance']} | {r['evidence_level']} | "
            f"{r['disease']} | PMID: {r['pmid']} ({r.get('citation_text', '')})"
            for r in state.get("variant_data", {}).get("evidence_records", [])
        ),
    ]

    if state.get("drug_candidates"):
        ctx.append("=== DRUG CANDIDATI ===\n" + "\n".join(
            f"- {r['drug_name']} (approvato: {r['approved']})"
            + (f" | CompDiag: {r['companion_diagnostic']}" if r.get("companion_diagnostic") else "")
            + f" | Livello: {r['evidence_level']}"
            for r in state["drug_candidates"]
        ))

    if state.get("resistance_data"):
        ctx.append("=== PROFILO DI RESISTENZA ===\n" + "\n".join(
            f"- Variante: {r.get('variant', state['variant'])} | Livello: {r['evidence_level']} | PMID: {r['pmid']} ({r.get('citation_text', '')})\n"
            f"  {r['statement'][:300]}..."
            for r in state["resistance_data"]
        ))

    if state.get("trial_candidates"):
        ctx.append("=== TRIAL CLINICI ===\n" + "\n".join(
            f"- {r['nct_id']} | {r['title']} | Fase {r['phase']} | {r['status']}"
            for r in state["trial_candidates"]
        ))

    ctx.append(
        "=== PMID VERIFICATI NEL KNOWLEDGE GRAPH ===\n" + (
            "\n".join(f"- {pmid}: {text}" for pmid, text in verified_map.items())
            if verified_map else "(nessuno verificato)"
        )
    )

    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content="\n\n".join(ctx)),
    ])

    report_filtrato, pmid_rimossi = filtra_pmid_non_verificati(
        response.content,
        set(verified_map.keys())
    )

    if pmid_rimossi:
        print(f"[SYNTHESIZER] Rimossi {len(pmid_rimossi)} PMID non verificati dal testo: {pmid_rimossi}")

    return {
        **state,
        "report": report_filtrato,
        "cited_pmids": list(verified_map.keys()),
        "pmid_rimossi_dal_testo": pmid_rimossi,
    }
