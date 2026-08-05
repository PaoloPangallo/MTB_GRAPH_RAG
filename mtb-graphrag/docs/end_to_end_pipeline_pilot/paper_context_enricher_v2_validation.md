# Validazione semantica v2.0

`PaperContextEnrichmentV2Validator`, classe separata, non sostituisce né
modifica il validatore v1 (`enrichment_validator.py`, invariato — hash
confermato da `V1UnchangedTests`).

**Decision=QUOTE**: controlla `source_unit_id` non vuoto/esistente/
appartenente al paper, quote non vuota/letterale/continua (nessuna
ellissi), quote non presa da CaseContext o candidate (controllo di
leakage), passaggio pertinente alla drug richiesta, summary (se presente)
grounded nella quote e privo di raccomandazioni cliniche o linguaggio di
status/gate. Un summary vuoto **non invalida** una quote altrimenti
valida (`ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY`).

**Decision=ABSTAIN**: non crea mai un enrichment positivo.
`abstention_reason` atteso non vuoto. Se il modello ha comunque popolato
`source_unit_id`/`author_claim_quote`/`author_context_summary`, l'esito è
`ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS` — registrato per
audit, mai promosso, mai usato nel dossier, mai reinterpretato
automaticamente come `decision=QUOTE`.

## Risultati (7 chiamate)

| Esito | Conteggio |
|---|---:|
| `ENRICHMENT_V2_ACCEPTED` | 2 |
| `ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY` | 0 |
| `ENRICHMENT_V2_ABSTAINED` | 2 |
| `ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS` | 2 |
| `REJECTED_QUOTE_NOT_FOUND` | 1 |
| altri rigetti (`REJECTED_SOURCE_UNIT`, `REJECTED_QUOTE_NON_CONTIGUOUS`, `REJECTED_CONTEXT_MISMATCH`, `REJECTED_SUMMARY_UNGROUNDED`, `REJECTED_CLINICAL_RECOMMENDATION`) | 0 |

Il singolo rigetto (Caso 2, primo paper) è dovuto a una quote non
letteralmente presente nella SourceUnit dichiarata — il modello ha
scelto `decision=QUOTE` ma la citazione non superava il controllo di
fedeltà testuale; correttamente bloccata, non promossa. Le 2 astensioni
con campi incoerenti (`source_unit_id` popolato nonostante
`decision=ABSTAIN`) sono registrate per audit ma non hanno mai prodotto
evidenza positiva.

Zero quote inesistenti accettate, zero SourceUnit inventate accettate
(verificate indipendentemente contro il testo reale, non fidandosi
dell'esito del validatore — `run_pilot_v2.py::detect_hard_stops_v2`),
zero summary non grounded accettati, zero raccomandazioni cliniche
accettate.
