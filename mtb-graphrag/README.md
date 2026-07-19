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

## Avvio

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r backend/config/requirements.txt
uvicorn backend.api.main:app --reload
```

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
