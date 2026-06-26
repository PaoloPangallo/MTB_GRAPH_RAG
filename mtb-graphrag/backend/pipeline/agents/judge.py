"""
LLM-as-Judge — Valutazione separata dei report MTB.
Usa lo stesso modello della pipeline (Gemma 4 31B) come fallback.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from backend.pipeline.llm import llm_judge


JUDGE_SYSTEM = """Sei un valutatore esperto di sistemi AI per oncologia clinica.
Valuta il report MTB (Molecular Tumor Board) fornito secondo questi quattro criteri (punteggio da 1.0 a 5.0 per ciascuno):

1. COMPLETEZZA: il report copre variante, terapia, resistenze e trial in modo esaustivo? (Ispirato alla metrica "Comprehensiveness" di Edge et al., GraphRAG Microsoft)
2. UTILITÀ CLINICA: il report è immediatamente utilizzabile e actionable per un oncologo al board? La struttura scompare come criterio separato ed è assorbita qui, poiché un report mal strutturato non è actionable. (Adattamento della metrica "Empowerment" di Edge et al.)
3. FEDELTÀ ALLE EVIDENZE: i codici PMID citati sono presenti nel report e pertinenti alle raccomandazioni? (Ispirato alla metrica "citation precision" di Wu et al.)
4. ACCURATEZZA CLINICA: le raccomandazioni terapeutiche e le informazioni scientifiche fornite nel report sono clinicamente corrette? (Criterio originale, in sostituzione di "Struttura" che è banale)

Restituisci un JSON con questa struttura esatta:
{
  "completezza": <1.0-5.0>,
  "utilita_clinica": <1.0-5.0>,
  "fedelta_evidenze": <1.0-5.0>,
  "accuratezza_clinica": <1.0-5.0>,
  "score_totale": <media dei 4 criteri>,
  "motivazione": "<spiegazione sintetica dei punteggi assegnati>"
}
"""


def llm_as_judge(report: str, case_info: dict) -> dict:
    """Valuta un report MTB con LLM-as-judge."""
    user_msg = (
        f"Caso: {case_info.get('gene')} {case_info.get('variant')} / "
        f"{case_info.get('tumor_type')}\n\n"
        f"Report da valutare:\n{report}"
    )
    response = llm_judge.invoke([
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=user_msg),
    ])
    try:
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            content = "\n".join(lines).strip()
        
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            content = content[start:end+1]
            
        return json.loads(content)
    except Exception:
        return {"raw_response": response.content, "error": "parsing fallito"}
