# 11 — RQ4 rieseguito

## Metodo

Benchmark congelato **invariato**: `benchmark_sha256` è verificato a ogni
esecuzione, e input, gold, categorie e attese non sono stati toccati.

```
frozen_rq4_benchmark_modified = false
parser_calls_executed         = 0
```

Gli output del parser sono **riusati** da
`evaluation/rq4_casecontext_robustness/run_outputs.jsonl`. Il parser e il suo
prompt non sono cambiati: riusarli isola l'effetto dei nuovi stage
deterministici — che è esattamente ciò che si vuole misurare — e non consuma
budget per riottenere gli stessi output. Sugli output riusati vengono eseguiti
verifica testuale, verifica semantica, rilevamento delle istruzioni di
controllo, rilevamento delle contraddizioni ed eligibility gate.

## Prima e dopo

| Metrica pre-specificata | Prima | Dopo |
|---|---|---|
| `symptom_copied_into_disease_field` | 5 | **0** |
| `injected_drug_extracted_as_target` | 1 | **0** |
| `empty_casecontext_retrieval` | — (il gate non esisteva) | **0** |
| `contradictory_case_retrieval` | 5 | **0** |
| `out_of_scope_retrieval` | 3 | **0** |
| `non_actionable_retrieval` | 4 | **0** |
| `forbidden_downstream_calls` | 0 | **0** |
| `control_instruction_execution` | 0 | **0** |
| Esiti di routing distinti | **2** | **7** |

I valori «prima» per out-of-scope, non-actionable e contradictory sono il numero
di casi che, con il solo `essential_fields_pass`, proseguivano al retrieval.

## Il cambiamento qualitativo

Nell'esecuzione originale esistevano **due soli esiti di routing** e la categoria
dell'input non li determinava: dove gli input fuori dominio si fermavano, si
fermavano perché il *modello* non produceva una tool call conforme.

Ora **27 dei 35 casi si fermano al gate**. Di questi, 18 si fermerebbero anche se
il modello producesse una tool call perfettamente valida: la fermata è una
proprietà dell'architettura, non del comportamento del modello.

Gli 8 eleggibili sono 4 `IN_SCOPE_COMPLETE`, 2 `IN_SCOPE_INCOMPLETE`, 1
`AMBIGUOUS` (contiene disease e gene reali) e 1 `ADVERSARIAL` (`G5`, che porta un
caso clinico genuino accanto alla direttiva iniettata).

## Metriche post-hoc

Le metriche dell'esecuzione originale — offset validity, field precision/recall,
null preservation, ripetibilità — restano in
`evaluation/rq4_casecontext_robustness/` e **non** sono state ricalcolate:
riguardano il parser, che non è cambiato. Tenerle separate dalle metriche
pre-specificate del gate è la ragione per cui questo report non le ripete.

## Limite di questa riesecuzione

Riusare gli output del parser significa che i 9 casi in cui il modello non ha
prodotto una tool call conforme (`FORCED_TOOL_IGNORED` 5,
`INVALID_TOOL_ARGUMENTS` 4) restano tali. Il gate li classifica
`INVALID_INPUT`, che è corretto, ma non dimostra come li tratterebbe se il
modello avesse risposto. Per quei 9 casi il risultato è ancora determinato dal
comportamento del modello, non dal gate.
