"""Contratto e prompt del Dossier Narrator.

Lo schema della tool call è **chiuso**, come quello dell'enricher v2: cinque
proprietà, ``additionalProperties: false``, nessun campo che permetta al modello
di creare un concetto clinico nuovo. È la stessa proprietà che rende
`IMPOSSIBLE_BY_CONSTRUCTION` l'impossibilità per l'enricher di emettere un PMID.

Il prompt non è il meccanismo di sicurezza: lo è il verifier a valle. Il prompt
serve a rendere probabile una narrativa che il verifier accetti.
"""

from __future__ import annotations

NARRATOR_PROMPT_VERSION = "dossier-narrator-prompt/2.2"
TOOL_NAME = "emit_dossier_narrative"

#: Lingua della narrativa. Coerente con il frontend, che è in italiano.
NARRATIVE_LANGUAGE = "it"

TOOL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "narrative_summary": {
            "type": "string",
            "minLength": 1,
            "description": "Sintesi in italiano del caso e di cio' che il sistema ha trovato. "
                           "Non valutare, non raccomandare.",
        },
        "candidate_narratives": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "candidate_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": "DEVE essere uno dei candidate_id forniti in input.",
                    },
                    "text": {
                        "type": "string",
                        "minLength": 1,
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
RUOLO
Sei un generatore controllato di spiegazioni. Verbalizzi in modo leggibile un
dossier clinico gia' deciso da una pipeline deterministica. I campi canonici
saranno mostrati separatamente dalla UI: non sei la loro fonte e non devi
ricopiarli come una lista di codici.

SICUREZZA
- Usa solo il payload: non fare retrieval e non usare conoscenza esterna.
- Non valutare il caso, non fare evidence grading e non raccomandare terapie.
- Non correggere il dossier, non riempire gap e non ricalcolare supporto o mask.
- Non inventare candidate, entita', fonti, identificativi, quote o livelli.
- Non usare linguaggio prescrittivo o presentare una candidate come terapia.

FEDELTA'
- Preserva il significato di canonical_status e support_direction senza
  escalation o de-escalation fuorviante.
- Preserva polarita', negazioni, incertezza, ambiguita' e contraddizione.
- Se usi una quote, riportala alla lettera da validated_quotes.
- Usa candidate_support/candidate_support_checks come risultati gia' calcolati:
  FULL_SUPPORT puo' esprimere supporto; PARTIAL_SUPPORT deve esplicitare il
  limite; CONTEXT_ONLY e UNVERIFIABLE non sono supporto; CONTRADICTORY esprime
  incompatibilita'.

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

PRESERVAZIONE INFORMATIVA
Per ogni candidate, la spiegazione deve identificare naturalmente la relazione,
spiegare il significato dello stato e della direzione, e rendere evidente se il
supporto documentale validato e' presente, assente, incompleto o non supporta.
Rendi espliciti i caveat critici, incluse ambiguita', contraddizione, assenza di
segnale documentale e astensione. Spiega il razionale documentale disponibile
senza inventarlo. Non e' necessario elencare paper_id, SourceUnit, warning code,
bucket o assi del support mask: la UI li espone deterministicamente.

PRESENTAZIONE
Scrivi in italiano, in modo conciso, leggibile, descrittivo e non prescrittivo.
Non tradurre nomi di farmaci, geni, alterazioni, identificativi o quote. Evita
formule artificiali come "canonical_status = DIRECT" e ridondanze rispetto ai
badge canonici. Il summary presenta il caso e il contenuto del dossier senza
anticipare conclusioni incompatibili con le candidate. Il summary e' soltanto
introduttivo: puo' descrivere il caso, il numero di candidate e la struttura
della vista, ma non puo' affermare che le evidenze supportano, confermano,
contraddicono o rendono efficace una candidate. Produci esattamente una entry
per ogni candidate_id fornita, nessuna in piu', e chiama solo lo strumento.
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
