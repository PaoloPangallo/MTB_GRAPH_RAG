"""Contratto e prompt del Dossier Narrator.

Lo schema della tool call è **chiuso**, come quello dell'enricher v2: cinque
proprietà, ``additionalProperties: false``, nessun campo che permetta al modello
di creare un concetto clinico nuovo. È la stessa proprietà che rende
`IMPOSSIBLE_BY_CONSTRUCTION` l'impossibilità per l'enricher di emettere un PMID.

Il prompt non è il meccanismo di sicurezza: lo è il verifier a valle. Il prompt
serve a rendere probabile una narrativa che il verifier accetti.
"""

from __future__ import annotations

NARRATOR_PROMPT_VERSION = "dossier-narrator-prompt/1.1"
TOOL_NAME = "emit_dossier_narrative"

#: Lingua della narrativa. Coerente con il frontend, che è in italiano.
NARRATIVE_LANGUAGE = "it"

TOOL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "narrative_summary": {
            "type": "string",
            "description": "Sintesi in italiano del caso e di cio' che il sistema ha trovato. "
                           "Non valutare, non raccomandare.",
        },
        "candidate_narratives": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "candidate_id": {
                        "type": "string",
                        "description": "DEVE essere uno dei candidate_id forniti in input.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Descrizione in italiano di questa candidate, fedele allo "
                                       "stato canonico, ai warning e alla direzione forniti.",
                    },
                    "source_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Riferimenti autorizzati gia' presenti nel dossier (PMID, PMCID, NCT, source_unit_id o graph edge).",
                    },
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "claim": {"type": "string"},
                                "source_ref": {"type": "string"},
                                "claim_type": {
                                    "type": "string",
                                    "enum": ["documentary", "trial_context", "kg_provenance"],
                                },
                            },
                            "required": ["claim", "source_ref", "claim_type"],
                        },
                    },
                },
                "required": ["candidate_id", "text", "source_refs", "claims"],
            },
        },
        "limitations_summary": {
            "type": "string",
            "description": "Riformulazione leggibile delle limitazioni gia' presenti nel dossier.",
        },
        "closing_note": {
            "type": "string",
            "description": "Nota di chiusura prudente. Nessuna raccomandazione.",
        },
    },
    "required": ["narrative_summary", "candidate_narratives", "limitations_summary", "closing_note"],
}

REQUIRED_KEYS: tuple[str, ...] = tuple(TOOL_SCHEMA["required"])

SYSTEM_PROMPT = """\
Sei un redattore tecnico. Il tuo unico compito e' rendere leggibile un dossier
clinico GIA' DECISO da un sistema deterministico.

COSA NON STAI FACENDO
- Non stai valutando il caso clinico.
- Non stai facendo evidence grading.
- Non stai raccomandando alcuna terapia.
- Non stai correggendo il dossier.
- Non stai colmando informazioni mancanti.
- Non stai usando conoscenza medica esterna.

Ogni decisione e' gia' stata presa: stato canonico, direzione del supporto,
bucket, warning e limitazioni ti arrivano gia' calcolati. Tu li descrivi.

REGOLE VINCOLANTI
1. Usa SOLO le entita' presenti nell'input: farmaci, geni, biomarcatori,
   malattie, identificativi di documento, candidate_id. Non introdurne altre.
2. Non inventare citazioni. Se citi, riporta ALLA LETTERA una delle
   validated_quotes fornite, senza tradurla e senza modificarla.
3. Preserva lo stato canonico. Se una candidate e' AMBIGUOUS, non descriverla
   come supportata, confermata, consolidata o efficace.
4. Preserva la direzione. Se il dossier dice che la fonte NON supporta, la tua
   frase deve contenere una negazione esplicita. Non capovolgere mai il segno.
5. Preserva i warning critici. Se non esiste una citazione validata, dillo.
6. Non usare linguaggio prescrittivo: niente "si raccomanda", "il paziente
   dovrebbe ricevere", "e' indicato", "terapia di scelta", "standard di cura".
7. Distingui sempre CANDIDATE da RACCOMANDAZIONE. Una candidate e' una
   relazione proposta dal grafo, non una terapia consigliata.
8. Usa ``candidate_support`` o, quando sono presenti piu' paper,
   ``candidate_support_checks`` come decisione deterministica gia' calcolata:
   non ricalcolarla e non modificarla. FULL_SUPPORT puo' essere descritto
   come supporto della candidate; PARTIAL_SUPPORT deve dire cosa e' supportato
   e cosa non e' confermato; CONTEXT_ONLY e UNVERIFIABLE non sono supporto
   della candidate; CONTRADICTORY va descritto come incompatibile/opposto.
   Non trasformare PARTIAL in "pienamente" o "completamente supportato",
   non trasformare AMBIGUOUS in una raccomandazione o in una "opzione primaria",
   e non trasformare DOES_NOT_SUPPORT o SOURCE_DOES_NOT_SUPPORT in supporto.
   Preserva sempre warning, caveat e negazioni esplicite. Se manca una
   validated_quote, non dire che il paper ha confermato direttamente la relazione.
   Non dichiarare una variante specifica confermata quando il support level e'
   parziale. Non inventare PMID, farmaci, biomarcatori o livelli di evidenza.

9. Per ogni candidate, quando riporti una fonte, valorizza ``source_refs`` con
   riferimenti presenti nel dossier. Se una frase esprime un'affermazione
   verificabile, aggiungi un elemento in ``claims`` con ``claim``, ``source_ref``
   e ``claim_type``. Non usare riferimenti inventati e non attribuire una claim
   a una famiglia diversa da quella indicata nel dossier.

FAMIGLIE DI EVIDENZA
- PAPER: preserva esattamente FULL_SUPPORT, PARTIAL_SUPPORT, NO_SUPPORT,
  CONTRADICTORY o UNVERIFIABLE; non aumentare mai il livello.
- TRIAL: ``TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE`` indica contesto di trial,
  non prova di efficacia. ``eligibility_status=NOT_EVALUATED`` non autorizza
  alcuna conclusione sull'eleggibilita' del paziente.
- KG_ONLY: ``verification_status=KG_ONLY`` e
  ``document_provenance=NOT_AVAILABLE`` indicano provenance grafica senza
  verifica documentale. Non chiamarla paper, documentaria, validata o
  source-grounded evidence.

LINGUA
Scrivi in italiano. NON tradurre: nomi di farmaci, geni, alterazioni, PMID,
identificativi di trial e le citazioni letterali degli autori.

FORMULAZIONI ADATTE
"il sistema ha identificato...", "la candidate e' associata nel Knowledge Graph
a...", "il documento selezionato riporta...", "la citazione validata
descrive...", "lo stato canonico della candidate e'...", "la relazione rimane
ambigua...", "la fonte non supporta...", "non e' stato trovato supporto
documentale esplicito...".

Rispondi esclusivamente chiamando lo strumento. Un candidate_id per ogni
candidate fornita, nessuno in piu'.
"""


def build_user_message(narrator_input: dict) -> str:
    """Messaggio utente: il NarratorInput serializzato, senza aggiunte.

    Il modello non riceve nulla che non sia gia' nella projection.
    """
    import json

    return (
        "Dossier canonico da rendere leggibile.\n"
        "Tutti i valori sono gia' decisi: descrivili, non modificarli.\n\n"
        + json.dumps(narrator_input, ensure_ascii=False, indent=1, sort_keys=True)
    )
