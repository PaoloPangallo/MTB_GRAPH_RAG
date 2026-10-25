# 13 — Decisione sullo switch a v3

## Criteri del §24

| # | Criterio | Esito |
|---|---|---|
| 1 | Loader v3 valido | ✅ manifest, contract_version, repository hash, lineage, enum e AST validati |
| 2 | Tutti gli invarianti passano | ✅ 0 violazioni su 46 142 candidate |
| 3 | Eligibility gate attivo | ✅ `stage_3b`, deterministico, nel contratto |
| 4 | Source polarity gestita | ✅ 4 rami distinti, verificato sull'intero repository |
| 5 | Compound alteration match integrato | ✅ AND/OR, PARTIAL mai promosso a FULL |
| 6 | Unresolved regimen policy integrata | ✅ rejection in evaluation, audit-only in discovery |
| 7 | Benchmark RQ4 supera i criteri critici | ✅ tutte e 8 le metriche = 0 |
| 8 | Shadow comparison completato | ✅ 35 casi |
| 9 | Nessun audit-only nel positivo | ✅ verificato da test |
| 10 | Nessun hard stop | ✅ nessuno |
| 11 | Test completi verdi | ✅ backend 3 047, frontend 195, evaluation 91 |

## Decisione

**Il default resta `GRAPH_CANDIDATE_REPOSITORY_VERSION=2.0`.**

```
research_runtime_default_repository = "2.0"
runtime_default_changed_to_v3       = false
```

I criteri formali sono soddisfatti, ma tre condizioni sostanziali non lo sono, e
nessuna delle tre è verificabile da un test:

### 1. Il ponte dei bundle non è stato validato clinicamente

Gli EvidenceBundle sono chiavizzati sugli id v2. Il ponte via `v2_mapping.jsonl`
è corretto per costruzione, ma associa il bundle di una candidate a farmaco
singolo alla **unità di regime** che la contiene. È la stessa relazione
rappresentata diversamente — e nessuno l'ha ancora verificata caso per caso.

### 2. Il campione manuale v3 non è annotato

70 record pronti in `evaluation/gold/rq1_gca_v3_manual_review.csv`, colonne del
revisore vuote. La fedeltà semantica di v3 è dimostrata rispetto ai **metadati**
della sorgente, non a un giudizio esperto.

### 3. Il retrieval v3 non è stato eseguito end-to-end fino al dossier

L'integrazione arriva fino a `CandidateRuntimeAdmission`. Il percorso
Document Resolution → SourceUnit → Paper Selection → Enricher → Validator →
Dossier **non** è stato eseguito con candidate v3, e la separazione dei rami nel
dossier è definita ma non esercitata su dati reali.

## Cosa è già attivo, indipendentemente dallo switch

L'eligibility gate è nel contratto e **si applica a entrambe le versioni**: i
difetti 4–10 dell'audit sono corretti già con il default `2.0`. Lo switch
riguarda solo i difetti 1–3, che sono proprietà del repository.

Questa è la ragione per cui il gate è stato integrato separatamente dal cambio
di default: il beneficio maggiore non dipendeva da v3.

## Condizioni per lo switch

1. annotare il campione manuale a 70 record;
2. eseguire il percorso completo fino al dossier con v3 sui cinque casi
   sintetici, verificando la separazione dei rami;
3. validare il ponte dei bundle su almeno i 16 candidate coinvolti;
4. decidere esplicitamente come il dossier presenta le 873
   `SOURCE_DOES_NOT_SUPPORT` e le 161 `SOURCE_NEUTRAL` a un clinico.

Il punto 4 resta il più importante: v3 rende visibile una popolazione che v2
nascondeva, il runtime ora la instrada nel ramo giusto, ma **come mostrarla a un
medico** è una decisione di prodotto che nessun test può prendere.

## Legacy

```
legacy_runtime_repository = "1.4"
```

La Legacy V3 continua a usare il proprio repository storico e non è stata
toccata.

## Nessun fallback

```
fallback_enabled = false
```

Una versione non supportata solleva `RepositoryVersionUnsupported`; un contratto
non valido solleva `RepositoryContractInvalid`. Non esiste un percorso v3 → v2.
