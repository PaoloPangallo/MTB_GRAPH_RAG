# evaluation/ — valutazione sperimentale RQ1–RQ4

Codice e artefatti della valutazione dell'architettura della verifiable research
pipeline. Il pacchetto è **read-only** rispetto al runtime: importa i moduli
canonici quando deve eseguirli, non li duplica e non li modifica.

I report discorsivi per la tesi stanno in [`../docs/evaluation/`](../docs/evaluation/).
Il protocollo, con la distinzione fra i quattro livelli di "correttezza", è in
[`01_evaluation_protocol.md`](../docs/evaluation/01_evaluation_protocol.md) e va
letto prima dei risultati.

## Esecuzione

```bash
cd mtb-graphrag

python -m evaluation.run_rq1            # fedeltà + completezza delle candidate
python -m evaluation.build_rq1_sample   # campione manuale RQ1 (50 righe)
python -m evaluation.run_rq2            # audit delle associazioni candidate–PMID
python -m evaluation.build_rq2_sample   # campione manuale RQ2 (50 coppie)
python -m evaluation.freeze_rq4         # congela il benchmark CaseContext
python -m evaluation.run_rq4            # smoke 35 casi (chiama l'LLM)
python -m evaluation.run_rq4_repeat     # repeatability 5 casi x 3 run
```

`run_rq4` e `run_rq4_repeat` effettuano chiamate reali al provider LLM e
richiedono `OLLAMA_API_KEY`. Tutti gli altri comandi sono offline.

## Struttura

| Percorso | Contenuto |
|---|---|
| `rq1/` | chiave canonica, riderivazione indipendente dal KG, confronto, campionamento |
| `rq2/` | normalizzazione PMID, provenance, risoluzione bibliografica |
| `rq3/` | piano di query OncoKB (nessuna chiamata senza licenza e autorizzazione) |
| `rq4/` | benchmark CaseContext, harness del parser, metriche |
| `gold/` | campioni per annotazione umana — **le colonne del revisore restano vuote** |
| `tests/` | test del codice di valutazione |
| `rq*_.../` | artefatti prodotti dalle run |

## Principi vincolanti

* **Nessun LLM come gold standard.** Le metriche derivano da confronto
  deterministico, gold congelato, annotazione umana o validatori già definiti. Un
  eventuale uso di LLM come analisi secondaria è etichettato
  `SHADOW_LLM_REVIEW_NOT_GOLD` ed escluso dalle metriche principali.
* **Nessun confronto tautologico.** I path eleggibili di RQ1 sono riderivati
  dall'export CSV, non ottenuti rieseguendo il materializzatore.
* **Gold congelato prima dell'esecuzione.** Il benchmark RQ4 è sigillato con hash
  e commit prima della prima chiamata al parser, e non è stato modificato dopo.
* **Nessun segreto negli artefatti.** Token e credenziali non compaiono in nessun
  file prodotto; un test lo verifica.
* **Nessun testo documentale integrale** e nessun dato reale di paziente.

## Stato

| RQ | Oggetto | Stato |
|---|---|---|
| RQ1 | Fedeltà e completezza delle GraphCandidateAssertion | misurato full-corpus |
| RQ2 | Validità e pertinenza dei PMID | struttura e risolvibilità misurate; pertinenza semantica in attesa di annotazione umana |
| RQ3 | OncoKB come sorgente di citazioni candidate | audit di fattibilità e licenza |
| RQ4 | Robustezza del CaseContext Parser | benchmark congelato ed eseguito |
