# Gate strutturale per dominio

Versione: `claim_structural_gate/1.1`
Output: `qualified_claim_retrieval_result/1.1`

## Cosa aggiunge al gate 1.0

Una decisione che viene prima di tutte le altre: il dominio del claim e quello
della query devono corrispondere.

Non è un filtro più fine dello stesso genere di quelli che c'erano. Il gate 1.0
decide se un claim terapeutico *risponde bene* a una query terapeutica; questo
decide se le due cose parlano della stessa domanda. Una query diagnostica che
restituisse un claim terapeutico non commetterebbe un errore di ranking ma un
errore di categoria, e gli errori di categoria non si vedono guardando i
punteggi: il risultato sembra ragionevole, è solo la risposta a un'altra domanda.

## Ordine di valutazione

1. generazione dei candidati (perimetro nativo);
2. dominio della query;
3. **dominio del claim contro dominio della query**;
4. perimetro nativo, anche in caso di disallineamento;
5. match strutturale — quello 1.0 per i terapeutici, biomarcatore e disease per
   i non terapeutici;
6. invarianti dell'oggetto (deprecato);
7. bucket e sezione;
8. **solo qui** un eventuale punteggio, e mai per i non terapeutici.

Il passo 4 esiste per una ragione misurata. Senza di esso, ogni query
diagnostica mandava in audit tutti e 146 i claim terapeutici, e il bucket
diventava illeggibile. Un claim di dominio sbagliato che parla anche di un altro
biomarcatore non è materiale di audit per quella query: è fuori perimetro. È lo
stesso argomento che il contratto 1.0 usa per i claim fuori perimetro, applicato
prima della differenza di dominio.

## Matrice

| Query | Primary eligible |
|---|---|
| `therapeutic_evidence_query` | solo claim terapeutici compatibili |
| `diagnostic_evidence_query` | solo `DiagnosticClaim` compatibili |
| `prognostic_evidence_query` | solo `PrognosticClaim` compatibili |
| `untyped_evidence_query` | tutti i domini, in sezioni separate |

Una query senza `query_domain` è **senza tipo**, non terapeutica: assumere il
dominio terapeutico per default rifarebbe, a un livello diverso, la scelta
implicita che tutta questa linea di lavoro esiste per togliere.

## Reason code

| Codice | Quando |
|---|---|
| `CLAIM_DOMAIN_QUERY_DOMAIN_MISMATCH` | disallineamento generico |
| `DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC` | diagnostico contro query terapeutica |
| `PROGNOSTIC_CLAIM_NOT_PREDICTIVE` | prognostico contro query terapeutica |
| `THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC` | terapeutico contro query diagnostica o prognostica |
| `UNTYPED_QUERY_REQUIRES_SECTIONED_RESULTS` | contratto della query senza tipo |
| `NON_THERAPEUTIC_CLAIM_HAS_NO_INTERVENTION_TO_MATCH` | query con intervento contro claim che non ne ha |

## Il divieto di ranking cross-domain

Non è sconsigliato: è impossibile. `rank_within_domain` solleva se riceve
risultati di domini diversi, e **non esiste** una funzione che ordini fra domini.
L'ordinamento è deterministico e non clinico — tipo di claim, graph evidence ID,
claim ID — perché serve alla serializzazione e ai test, non a una graduatoria.
Nessun punteggio numerico diagnostico o prognostico è stato introdotto.

## Scoring

| Vincolo | Stato |
|---|---|
| therapy score su claim non terapeutico | vietato, `therapy_score_forbidden: true` |
| intervention score | non applicabile |
| regimen / class score | non applicabile |
| eleggibilità strutturale | obbligatoria |
| qualification e provenance | esponibili |
| ranking cross-domain | vietato |

Nella simulazione, i claim non terapeutici che ricevono un therapy score sono
**0**, e il manifest lo riporta come conteggio derivato invece che come
affermazione.

## Simulazione sulle otto query

| Query | Scenario | Primari | Esito |
|---|---|---|---|
| D01 | diagnostic FGFR2-BICC1 | 1 | il claim diagnostico, senza therapy score |
| D02 | diagnostic FGFR2-AHCYL1 | 1 | il claim diagnostico, senza therapy score |
| T01 | therapeutic sulle stesse fusioni | 0 | 1 warning sull'aggregato; i diagnostici in audit con `DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC` |
| P01 | prognostic su `evidence:347` | 0 | nessun claim: il record non ne ha |
| U01 | untyped sulle fusioni FGFR2 | 2 | 1 diagnostico + 1 terapeutico, in sezioni separate |
| T02 | therapeutic EGFR L858R | 4 | solo terapeutici |
| T03 | therapeutic senza intervento | 21 | solo terapeutici |
| U02 | senza dominio | 22 | solo terapeutici, perché su quel perimetro non ci sono claim di altri domini |

I due diagnostici sono primari soltanto in D01, D02 e U01.

## Output 1.1

`subject_representation` sostituisce `intervention_representation` come campo
portante. Nel 1.0 un claim senza interventi poteva solo rispondere `none`:
corretto ma muto, diceva cosa il claim non ha invece di cosa afferma. Ora i
valori sono `atomic_intervention`, `regimen`, `intervention_class`,
`intervention_aggregate`, `diagnostic_subject`, `prognostic_subject`, `none`.

`intervention_representation`, `diagnostic_representation` e
`prognostic_representation` sono opzionali e presenti solo dove significano
qualcosa.

Ai quattro divieti del 1.0 se ne aggiunge uno: **nessun campo di intervento su un
claim che non ne ha uno, nemmeno nullo**. Un `intervention: null` in un dossier
invita a riempirlo, e riempirlo è l'errore da cui è cominciata tutta questa
linea di lavoro.

Per la query senza tipo l'output è sezionato: `therapeutic_results`,
`diagnostic_results`, `prognostic_results`, con `cross_domain_ranking: false` e
`cross_domain_score_comparison: false` dichiarati nel payload.
