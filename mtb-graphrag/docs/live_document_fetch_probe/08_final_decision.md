# Decisione

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## Decisione

```
LIVE_DOCUMENT_FETCH_FEASIBLE
```

## Criteri richiesti

| Criterio | Esito |
|---|---|
| PMID/PMCID/NCT ottenuti automaticamente dalla pipeline | ✅ dalla provenance della GCA |
| Test PubMed riuscito | ✅ 9 SourceUnit con testo |
| Test PMC riuscito | ✅ 243 SourceUnit, PMCID derivato da PubMed |
| SourceUnit create con testo | ✅ 0 fallimenti di parsing |
| Gemma raggiunta | ✅ 3 casi su 3 |
| Almeno una quote validata **oppure** ABSTAIN corretto | ✅ 2 quote verificate + 1 astensione corretta |
| Nessun input manuale di identificatori | ✅ |
| Nessuna modifica runtime necessaria per il test | ✅ |

## Invarianti

```
runtime_code_modified          = false
orchestrator_modified          = false
gca_modified                   = false
cache_miss_behaviour_modified  = false
fetch_on_miss_integrated       = false
historical_artifacts_modified  = false
real_cache_modified            = false
push_executed                  = false
merge_executed                 = false
```

## Nessun hard stop è scattato

| Condizione §14 | Verificata |
|---|---|
| PMID/PMCID devono essere forniti manualmente | no |
| La GCA non conserva provenance utile | no — porta i PMID |
| Mapping candidate → documento ambiguo | no — uno-a-molti dichiarato, `paper_selection` lo governa |
| Un fetch recupera un documento diverso | no — PMCID derivati coincidono con la baseline |
| Gemma riceve testo non collegato alla candidate | no — unità dal documento della provenance |
| Serve cambiare GCA/runtime per il test | no |
| Il validator non riesce a verificare la quote | no — offset ritrovati |
| Artefatti storici modificati | no |

## La riserva che conta

La sonda dimostra che **il documento** è recuperabile automaticamente. Non
dimostra che **il passaggio giusto dentro il documento** sia selezionabile
automaticamente: oggi quella scelta viene dai bundle congelati, che su un
documento recuperato al volo non esistono.

È l'anello scoperto, ed è descritto in
[07_architectural_implications.md](07_architectural_implications.md). Finché
resta scoperto, `cache-first / API-on-miss` non è implementabile end-to-end nel
runtime finale — non per un limite del recupero, ma per l'assenza di un
selettore di SourceUnit documentabile.

## Cosa questa decisione autorizza

Ad aprire il progetto del selettore di SourceUnit, e a istruire i rischi
elencati in §4 di quel documento.

**Non** autorizza modifiche al runtime canonico, che resta invariato e continua
a fallire in modo esplicito su cache miss.
