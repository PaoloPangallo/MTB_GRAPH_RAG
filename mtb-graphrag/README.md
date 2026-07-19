# MTB GraphRAG

Prototipo di ricerca per preparare evidenze revisionabili destinate a un
Molecular Tumor Board. Il sistema non produce decisioni terapeutiche autonome.

## Confronto delle architetture

La schermata **Confronta architetture** applica lo stesso caso a:

1. traversal deterministico: piano fisso, query tipizzate, LLM a valle;
2. orchestrazione agentica: routing condizionale, piu strumenti e controllo
   esplicito delle claim nella modalita dimostrativa.

La modalita `demo` funziona senza servizi esterni ed espone una fixture
dichiarata. La modalita `live` richiede Neo4j e l'endpoint LLM configurati; la
UI mostra esplicitamente che event log e verificatore end-to-end non sono
ancora completamente integrati nel backend corrente.

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

## Sicurezza e riproducibilita

- non committare `.env`, password, token o casi clinici identificabili;
- usare solo casi sintetici/pubblici nella demo;
- conservare gli artefatti pesanti fuori da Git con checksum;
- considerare `claim support` come supporto rispetto al ledger, non come
  accuratezza clinica.

Gli script della tesi sono in `experiments/reproducibility/` con una nota sugli
artefatti richiesti.
