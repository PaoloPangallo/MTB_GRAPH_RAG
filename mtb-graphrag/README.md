# MTB GraphRAG

Prototipo di ricerca per preparare evidenze revisionabili destinate a un
Molecular Tumor Board. Il sistema non produce decisioni terapeutiche autonome.

## Confronto delle architetture

La schermata **Confronta architetture** applica lo stesso caso a:

1. traversal deterministico: piano fisso, query tipizzate, LLM a valle;
2. architettura agentica verificabile: planner dinamico su strumenti allow-listed,
   ledger append-only, vista canonica, rendering deterministico e verifica
   claim--fonte.

La modalità `demo` funziona senza servizi esterni ed espone una fixture
dichiarata. La modalità `live` richiede Neo4j, l'endpoint LLM configurato e
accesso a PubMed. Ogni decisione e tool call viene inserita durante
l'esecuzione in un ledger SQLite append-only con catena SHA-256. Le claim sono
ammesse nel report soltanto dopo il confronto con record CIViC e abstract
PubMed; esiti incerti o fonti non disponibili vengono inviati alla revisione
umana.

## Dossier clinico comparativo

Il confronto accetta, oltre al profilo molecolare, stadio, setting di malattia,
trattamenti e risposta precedenti, ECOG, interessamento del SNC,
co-alterazioni, contesto regolatorio e obiettivo del MTB. I campi sono
facoltativi: quelli non compilati vengono mostrati come dati mancanti e non
sono ricostruiti dal modello.

Entrambe le architetture restituiscono lo stesso contratto di dossier:

- riepilogo del caso e dati mancanti;
- evidenze supportate documentalmente, con applicabilità clinica separata;
- evidenze da revisionare o non verificate;
- evidenze escluse con motivazione;
- resistenze e trial potenzialmente pertinenti;
- questioni da discutere nel Molecular Tumor Board.

Il dossier mantiene due assi distinti: supporto della claim rispetto alla fonte
e compatibilità con i dati clinici dichiarati. Se il caso è incompleto,
l'applicabilità resta indeterminata anche quando la fonte supporta la claim.

## Avvio

```bash
cp .env.example .env
python -m venv .venv           # Python 3.12
source .venv/bin/activate
pip install -r backend/config/requirements.txt
uvicorn backend.api.main:app --reload
```

Per **eseguire test ed evaluation** servono anche le dipendenze di sviluppo:
`requirements.txt` da solo non contiene `pytest`.

```bash
pip install -r backend/config/requirements-dev.txt
pytest                          # 3 189 test, nessun PYTHONPATH da impostare
```

`backend/config/requirements-lock.txt` congela l'ambiente esatto in cui gli
esperimenti sono stati eseguiti (`pip freeze`), per chi debba riprodurli alla
lettera.

In un secondo terminale:

```bash
cd frontend
npm ci
npm run dev
```

Aprire `http://localhost:5173` e scegliere **Confronta architetture**.

Per un deployment persistente, impostare `AGENT_LEDGER_PATH` su una directory
montata come volume. Il valore predefinito è `./data/agent_events.sqlite3`.

## Sicurezza e riproducibilità

- non committare `.env`, password, token o casi clinici identificabili;
- usare solo casi sintetici/pubblici nella demo;
- conservare gli artefatti pesanti fuori da Git con checksum;
- considerare `claim support` come esito di provenienza, regole cliniche e
  verifica semantica sulla fonte disponibile, non come sostituto della
  valutazione clinica dell'oncologo.

Gli script della tesi sono in `experiments/reproducibility/` con una nota sugli
artefatti richiesti.

## Le due architetture verificabili

Il sistema espone **due sole architetture GraphRAG complete**, che differiscono
soltanto nella strategia di raccolta e condividono per intero lo strato di
controllo (ledger, replay, vista canonica, proiezione, rendering, verifica
strutturale, verifica documentale, applicabilità, riparazione, dossier):

1. **GraphRAG deterministico verificabile** — piano fisso e traversal tipizzato.
2. **Agentic GraphRAG verificabile** — planner adattivo in ciclo plan–act–observe.

Dettagli in [`docs/THESIS_CODE_ALIGNMENT.md`](docs/THESIS_CODE_ALIGNMENT.md).

Il ledger è **append-only e tamper-evident nel threat model considerato**, non
immutabile in senso assoluto. Il dossier è un artefatto destinato alla revisione
del Molecular Tumor Board: questo è un **prototipo di ricerca** e non produce
raccomandazioni terapeutiche.

## Verifica

La suite **core** gira su qualunque checkout pulito, senza ingressi esterni e
senza saltare niente per la loro assenza:

```bash
# Test backend (unittest stdlib, nessun runner aggiuntivo configurato)
cd mtb-graphrag && PYTHONPATH=. python -m unittest discover -s backend/tests -t .
cd mtb-graphrag && PYTHONPATH=. python -m pytest backend/tests -q

# Frontend
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

### Ingressi esterni privati

Due ingressi non stanno nel repository e non ci staranno mai: il **bundle gold
pilota**, materiale clinico riservato, e la **cache degli abstract**, testo
protetto da copyright. Di entrambi il repository conserva il manifest — versione,
schema, hash attesi file per file, hash aggregato — che basta a verificarli
quando ci sono e a descriverli quando non ci sono.

I test che li aprono stanno fuori dalla discovery core, un albero per ingresso, e
si eseguono con un comando esplicito ciascuno:

```bash
python -m benchmarks.mtb_evidence.evaluation.run_gold_evaluation \
  --gold-bundle <PATH>

python -m benchmarks.mtb_evidence.evaluation.run_source_cache_validation \
  --source-abstract-cache <PATH>
```

Ogni comando verifica il **proprio** ingresso contro il manifest e poi esegue la
**propria** suite. Codici d'uscita: `2` ingresso assente (il messaggio dice dove
ha cercato), `3` ingresso presente ma diverso da quello dichiarato, `4` test
falliti. Il 3 e il 4 restano distinti apposta: un risultato calcolato su un
ingresso diverso da quello dichiarato non e' sbagliato, e' inconfrontabile.

### Impronte di integrità

`artifact_hash_policy/2.0` dichiara come si misura l'integrità di un file:
sempre da `read_bytes()`, forma canonica LF, e un CR isolato viene rifiutato
invece di essere convertito in silenzio. Dodici artefatti di otto fasi chiuse
portano impronte prese sotto la convenzione implicita precedente: non vengono
riscritte, sono registrate in
`benchmarks/mtb_evidence/v3/hermetic_reproducibility_closure/`.

## Migrazione del ledger

Lo schema v2 viene applicato automaticamente all'apertura del ledger. La
migrazione è **additiva**: `ALTER TABLE ADD COLUMN` non attiva i trigger
append-only e non riscrive le righe esistenti, che restano marcate `v1` e
continuano a verificare con il preimage originale.

```bash
# Ispezione dell'integrità di un run
PYTHONPATH=. python -c "from backend.pipeline.agentic.ledger import EventLedger; \
  print(EventLedger('data/agent_events.sqlite3').chain_report('<run_id>'))"
```

Consigliata una copia di `data/agent_events.sqlite3` prima del primo avvio con
lo schema v2, per prudenza sull'archivio di audit.

## Case study riproducibile

```bash
PYTHONPATH=. SOURCE_VERIFIER_MAX_WORKERS=6 \
  python experiments/thesis_alignment/run_case_study.py --live
```

Esegue EGFR L858R / Lung Adenocarcinoma / first-line / `general-review` su
entrambe le architetture, in fase cold e warm, con **cache isolata per
architettura** (altrimenti il cold della seconda sarebbe già caldo per effetto
della prima). I risultati sono etichettati come **run live**, distinte da test
con LLM scriptato, benchmark e case study descrittivo.
