# Decisione architetturale

## Verifica dei criteri di successo (sezione 19)

| Criterio | Esito |
|---|---|
| Parser produce CaseContext corretti nei casi espliciti | Sì (5/5, 25/25 span MATCH) |
| Verifier blocca/segnala il caso problematico | Sì (Caso 5: MATCH testuale corretto, blocco al retrieval) |
| Nessun MISMATCH essenziale raggiunge il retrieval | Sì (0 MISMATCH) |
| Retrieval trova le candidate attese | Sì (4/4 casi THERAPY_*) |
| Massimo due paper per associazione | Sì (7 paper su 4 associazioni, mai >2) |
| Gemma cita solo SourceUnit reali | Sì (vacuo: 0 citazioni accettate, 0 non valide accettate) |
| Quote inesistenti accettate = 0 | Sì |
| SourceUnit inventate accettate = 0 | Sì |
| Summary con fatti aggiuntivi accettati = 0 | Sì |
| Raccomandazioni cliniche prodotte = 0 | Sì |
| Caso contradicted non diventa positivo | Sì (Caso 4: AMBIGUOUS, mai DIRECT/CONTRADICTED senza prova) |
| Dossier distingue evidenza deterministica da contesto Gemma | Sì (verificato da test dedicato) |

## Decisione

**PIPELINE_INTERACTION_PILOT_PASSED**

La pipeline funziona end-to-end (testo libero -> dossier) su 5/5 casi con
il comportamento atteso (4 completati, 1 correttamente fermato) e mantiene
rigorosamente la separazione dei ruoli: Gemma non ha mai deciso status,
direction, contradiction, gate, score o bucket in nessuna delle 7
chiamate. Va letta insieme a `pilot_limitations.md`: nessuna run ha
prodotto un esempio positivo di citazione accettata, quindi il pilot
dimostra la **sicurezza e la meccanica architetturale** in modo solido, ma
non ancora la **resa pratica** del Paper Context Enricher su casi con
supporto disponibile.

## Problemi architetturali emersi

1. Il Match Verifier non deve fidarsi degli offset autoriportati dal
   modello come autorevoli (corretto durante il pilot).
2. Il matching biomarcatore nel retrieval deve considerare l'intero
   contenuto testuale del campo (`gene` + `normalized_value` + `raw_value`),
   non un singolo campo preferito (corretto durante il pilot).
3. Gemma produce occasionalmente un `evidence_kind` fuori enum
   (`EVIDENCE_KIND_INVALID`, 3/7 chiamate) — un limite di conformità allo
   schema del modello/transport, non di grounding.
4. Nessuna delle chiamate a trasporto valido ha prodotto una citazione
   accettata in questa run — il campione è troppo piccolo (4 chiamate
   valide) per giudicare se questo è sistematico o casuale.

## Modifiche raccomandate (da NON applicare ora, solo documentate)

- Valutare se rendere `evidence_kind` più tollerante lato adapter (es.
  normalizzare varianti testuali vicine all'enum prima del controllo
  schema) in una futura versione del prompt (`paper-context-enricher-prompt/1.1`),
  non durante questo pilot.
- Ripetere il pilot su un campione più ampio di paper con supporto atteso
  più diretto, per verificare se il Paper Context Enricher raggiunge mai
  `ENRICHMENT_ACCEPTED` con un budget di chiamate maggiore.

## Prossimo passo

Non integrare nel runtime clinico principale. Considerare uno smoke test
dedicato e più ampio del solo Paper Context Enricher (budget separato)
prima di qualunque ulteriore integrazione, per raccogliere almeno un
esempio positivo end-to-end validato.
