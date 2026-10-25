# Console della pipeline della tesi

Interfaccia React/TypeScript del runtime `backend/research_pipeline`, esposto da `/api/v1/research/pipeline`.

La route principale e `/research/verifiable-pipeline`; le run sono consultabili sotto `/research/verifiable-pipeline/runs/:runId`. Le vecchie route vengono reindirizzate alla console corrente.

Il risultato principale e il dossier canonico: pubblicazioni, studi clinici e relazioni del Knowledge Graph restano distinti. Il contratto `documentary-findings/1.0` presenta target, osservazioni estratte, controlli eseguiti e limiti separati. Le vecchie classificazioni restano nei dettagli tecnici dei record storici. Una citazione autentica non dimostra corrispondenza al target o efficacia clinica. La narrativa controllata e un approfondimento opzionale, riconciliato agli stessi fatti del dossier.

La sequenza degli stage comprende il gate di eleggibilita prima del retrieval. I dettagli di stage, la provenienza e le metriche consentono di ispezionare la run. La disponibilita della cache documentale riguarda i percorsi PAPER/TRIAL; KG_ONLY non richiede documenti. Il frontend non formula raccomandazioni terapeutiche e non valuta l'eleggibilita individuale ai trial.

## Sviluppo e verifica

```sh
npm ci
npm run dev
npm run typecheck
npm run lint
node node_modules/vitest/vitest.mjs run --maxWorkers=1
npm run build
```

La configurazione dell'API e definita in `src/apiBase.ts` tramite `VITE_API_BASE_URL`. Il backend deve abilitare `VERIFIABLE_PIPELINE_RESEARCH_ENABLED` per esporre il runtime.

## Architecture Explorer

La pagina `/architecture` è una simulazione autonoma e offline dell'architettura GCA4, separata dalla console e senza richieste al backend o a provider di modelli. Avviare `npm run dev` e aprire `http://localhost:5173/architecture`. Gli scenari DEMO illustrano retrieval RRF, mismatch strutturale, semantic alignment simulato, percorsi separati EVIDENCE_STATEMENT/TRIAL/KG_ONLY e fallback con dossier parziale. Per dettagli e test: [ARCHITECTURE_EXPLORER.md](./ARCHITECTURE_EXPLORER.md).

I test verificano il contratto canonico, la separazione fra validita della citazione e supporto, la disponibilita dei trial, gli stop controllati e la navigazione. La console V3, i confronti fra architetture e le dipendenze della visualizzazione 3D sono stati rimossi.
