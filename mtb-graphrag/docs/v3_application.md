# Integrazione Reale V3 Evidence-Centric Explorer

Documentazione tecnica dell'applicazione reale MTB-GraphRAG V3 sul corpus promosso `qualified_claim_repository/1.4` e gate `qualified_claim_structural_gate/1.3`.

---

## 1. Architettura Generale

L'applicazione integra realmente l'architettura V3 **evidence-centric** senza l'uso di dati sintetici o fixture applicative.

### Flusso Esecutivo Reale
1. **Frontend (React + TypeScript + Vite)**: L'utente inserisce una query strutturata nel form `V3QueryPanel`.
2. **API Client (`src/api/v3Api.ts`)**: Invia una richiesta HTTP POST a `/api/v1/v3/retrieve` configurabile via `VITE_API_BASE_URL`.
3. **Backend FastAPI (`backend/api/v3_routes.py`)**: Valida la richiesta con gli schemi Pydantic `V3RetrievalRequest`.
4. **Pipeline Orchestrator (`EvidenceRetrievalPipeline`)**: Invoca `pipeline.run(query, retrieval_backend="qualified_claim_v3")`.
5. **V3 Retriever (`QualifiedClaimRetrieverV3`)**: Legge il corpus promosso reale `qualified_claim_repository/1.4` tramite `backend.pipeline.evidence.corpus.loader`.
6. **Gate Strutturali Reali (`integrated_gates_v13`)**: Esegue la valutazione deterministica sui 10 stadi della pipeline.
7. **Classificazione nei 4 Bucket**: Suddivide lossless le claim qualificate nei bucket **Primary**, **Warning**, **Audit**, **Rejected**.
8. **Rendering Narrativo Opzionale (`POST /api/v1/v3/render`)**: Esegue la sintesi testuale unicamente a partire dalle claim già qualificate, senza alterare bucket o ranking.

---

## 2. API Endpoints V3 (`/api/v1/v3`)

### GET `/api/v1/v3/metadata`
Restituisce lo stato delle versioni del backend:
- `backend_identifier`: `qualified_claim_v3`
- `corpus_version`: `qualified_claim_repository/1.4`
- `corpus_digest`: Hash sha256 del manifest
- `gate_version`: `qualified_claim_structural_gate/1.3`
- `retriever_version`: `qualified_claim_retriever/1.0`
- `policy_mode`: `strict_verified`

### POST `/api/v1/v3/retrieve`
Input JSON (`V3RetrievalRequest`):
```json
{
  "domain": "therapeutic",
  "biomarker": "EGFR L858R",
  "disease": "Non-Small Cell Lung Cancer",
  "intervention": "Osimertinib",
  "policy_mode": "strict_verified"
}
```
Output JSON (`V3RetrievalResponse`):
```json
{
  "query_id": "q_app_a1b2c3d4",
  "summary": {
    "total": 311,
    "primary": 3,
    "warning": 0,
    "audit": 155,
    "rejected": 153
  },
  "buckets": {
    "primary": [...],
    "warning": [...],
    "audit": [...],
    "rejected": [...]
  },
  "metadata": {
    "corpus_version": "qualified_claim_repository/1.4",
    "gate_version": "qualified_claim_structural_gate/1.3",
    "elapsed_ms": 346
  }
}
```

### POST `/api/v1/v3/render`
Riceve le claim qualificate e produce il report narrativo opzionale con la nota obbligatoria:
**"Il modello genera il testo dalle claim già qualificate. Non determina retrieval, bucket o ranking."**

---

## 3. Guida all'Avvio

### Avvio Backend (FastAPI)
```bash
cd mtb-graphrag
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

### Avvio Frontend (Vite)
```bash
cd mtb-graphrag/frontend
npm run dev
```

---

## 4. Isolamento e Sicurezza del Gold Set

```typescript
real_v3_retriever_used = true
static_application_fixtures_used = false
backend_semantics_modified = false
corpus_modified = false
claims_modified = false
gates_modified = false
scoring_modified = false
gold_read_count = 0
official_runs_executed = 0
official_ledger_writes = 0
```
- Nessuna lettura o conteggio del gold set sperimentale.
- Nessuna scrittura nel ledger ufficiale dell'esperimento (`data/final_v3_eval_events.sqlite3`).

---

## 5. Esito dei Test
- **Backend API Tests**: `python -m unittest backend.tests.test_v3_api` ➔ **PASSED (3/3)**
- **End-to-End Real Queries**: `python backend/tests/verify_v3_e2e.py` ➔ **PASSED (200 OK su 3 query reali + 1 render)**
- **Frontend Unit Tests**: `npm test` ➔ **PASSED (31/31)**
- **Typecheck TypeScript**: `npm run typecheck` ➔ **PASSED (0 errori)**
- **Production Build**: `npm run build` ➔ **PASSED (1.54s)**
