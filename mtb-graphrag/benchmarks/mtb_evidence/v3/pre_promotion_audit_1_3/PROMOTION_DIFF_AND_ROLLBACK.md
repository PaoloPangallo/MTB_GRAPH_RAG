# Simulazione della promozione e piano di rollback

Niente di quanto segue e' stato eseguito. Il documento descrive che cosa
*cambierebbe*, e la promozione resta una decisione separata.

## Diff logico: corpus operativo → candidato promosso

Modalita': `separate_prototype_promotion`  
Target: `promoted_claim_corpus_candidate`  
File operativi modificati: **0**

| Voce | Valore |
|---|---:|
| file da creare | 8 |
| file da sostituire | 0 |
| righe da ritirare | 20 |
| righe da creare | 17 |
| ID modificati | 4 |
| qualification link toccati | 37 |
| statement del corpus operativo | 147 |

La promozione **non sostituisce** il corpus v2: lo affianca. I file
elencati sono nuovi, e nessuno di quelli operativi compare fra i
sostituiti. E' la ragione per cui `operational_retriever_migration_ready`
resta falso anche se il corpus fosse promosso: il retriever operativo non
sa leggere il secondo corpus, e affiancarlo non lo insegna.

### ID modificati

| Vecchio | Nuovo | Record | Ragione |
|---|---|---|---|
| `CLM-2175b95ae3113c4f5d97` | `CLM-8941c177da91f66ff93a` | `evidence:1846` | diagnostic_disease_scope_narrowing |
| `CLM-7056003a9bdef747f514` | `CLM-a7e1c40b794d2c4d4ca8` | `evidence:1847` | diagnostic_disease_scope_narrowing |
| `CLM-a7c903cf8d423f015e29` | `CLM-90e863f00f134fc3cd3d` | `evidence:1851` | terminology_canonicalization |
| `CLM-aae818bbc8ec735a255d` | `CLM-5071bb2d8657ac0fbed0` | `evidence:1853` | terminology_canonicalization |

### Incompatibilita' del retriever

| Superficie | Dettaglio |
|---|---|
| chiave di indicizzazione | il retriever operativo indicizza `evidence_statement_id`; i claim tipizzati hanno `claim_id` e un parent intermedio |
| disease matching | il matcher operativo conosce una nozione binaria di disease match e non le undici relazioni direzionali |
| bucket di uscita | il retriever non conosce i quattro bucket e non sa dove collocare un risultato audit-only |

### Incompatibilita' dello scoring

| Superficie | Dettaglio |
|---|---|
| ordine gate/scoring | lo scoring operativo penalizza dopo il ranking; il gate integrato esclude prima, e una penalita' non e' un'esclusione |
| flag di eleggibilita' | nessun peso operativo conosce `structural_score_eligible`: i flag del gate non hanno un consumatore |

### Cambi di schema delle metriche e del renderer

| Consumatore | Cambio |
|---|---|
| report renderer | i bucket diventano quattro e non piu' due |
| metriche di copertura | il conteggio dei risultati non e' piu' il conteggio dei claim |
| report renderer | l'intervento non e' sempre una stringa: aggregati e regimi vanno resi come insiemi |
| report renderer | i claim diagnostici non ricevono therapy score e non vanno ordinati con i terapeutici |
| report renderer | il bucket va mostrato, perche' un risultato in warning non e' un risultato in primary |

## Compatibilita' all'indietro

| Lookup | Risolvibile | Restituisce |
|---|---|---|
| legacy statement ID | **true** | claim tipizzato che sostituisce lo statement, o il ritiro che lo spiega |
| graph evidence ID | **true** | parent piu' i suoi claim, non un singolo statement |
| vecchio claim ID | **true** | redirect verso il claim che lo sostituisce |
| claim ritirato | **true** | deprecated_claims.jsonl per claim_id |

### `intervention: string`

Un client che si aspetta una stringa e riceve uno dei tre oggetti
seguenti non deve essere accontentato appiattendolo. L'appiattimento e'
l'errore che il modello tipizzato esiste per impedire, e rifarlo nel
formato di uscita lo rifarebbe per intero.

| Tipo | Claim | Riceve | Appiattirlo significherebbe |
|---|---:|---|---|
| `aggregate_intervention_claim` | 3 | insieme non separabile di membri | attribuire a un singolo farmaco un risultato che la fonte attribuisce all'insieme |
| `regimen_claim` | 3 | combinazione di componenti | trasformare un risultato di combinazione in un risultato di monoterapia |
| `diagnostic_claim` | 2 | nessun intervento: il claim non ne ha uno | far comparire un claim diagnostico in una lista di opzioni terapeutiche |

Appiattimento permesso dalla promozione: false

## Rollback

Eseguito: false  
Passi: **7**  
Claim deprecati conservati: **true**

| # | Passo | Cosa | Modo di fallire che previene |
|---:|---|---|---|
| 1 | snapshot degli artefatti operativi | copiare corpus, link e view operativi in una directory di snapshot e registrarne gli hash prima di qualunque scrittura | verificare l'hash dopo aver gia' perso lo stato precedente |
| 2 | promozione atomica | scrivere il corpus promosso in una directory nuova e spostare il puntatore in un'unica operazione | promozione parziale |
| 3 | verifica post-write | ricalcolare gli hash dei file scritti e confrontarli con quelli attesi dal manifest della promozione | scrittura riuscita ma contenuto diverso |
| 4 | rollback su hash mismatch | un solo hash discordante riporta il puntatore allo stato precedente senza altre valutazioni | rollback deciso a occhio |
| 5 | ripristino del corpus precedente | ripristinare i file dallo snapshot del passo 1 e riverificarne gli hash | corpus operativo perso |
| 6 | ripristino di link e view | ripristinare qualification_links.jsonl e qualified_evidence_views.jsonl dallo stesso snapshot | corpus ripristinato ma link e view rimasti al nuovo stato |
| 7 | conservazione dei log | i log della promozione e del rollback restano anche quando il rollback riesce: sono l'unica prova di cosa e' stato tentato | rollback senza traccia di cosa sia successo |

Il passo che di solito manca e' il primo. Uno snapshot preso dopo la
scrittura non e' uno snapshot: e' una copia del nuovo stato, e il
rollback che vi si appoggia ripristina esattamente cio' da cui si voleva
tornare indietro.

