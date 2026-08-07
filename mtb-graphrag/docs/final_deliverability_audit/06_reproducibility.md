# 06 — Riproducibilità

Dati: `evaluation/final_deliverability/reproducibility_final.csv`.

## Il percorso del revisore, oggi

```
clean clone
  → ENVIRONMENT   ✅  REPRODUCIBLE          (era PARTIAL / NOT_REPRODUCIBLE)
  → BACKEND TESTS ✅  REPRODUCIBLE          (era NOT_REPRODUCIBLE)
  → FRONTEND BUILD ✅ REPRODUCIBLE          (era NOT_REPRODUCIBLE)
  → RUNTIME       ✅  REPLAY riproducibile · LIVE con dipendenza dichiarata
  → EVALUATION    ✅  REPRODUCIBLE
  → METRICS       ✅  REPRODUCIBLE
```

Tre passaggi che l'audit precedente classificava non riproducibili sono ora
riproducibili. È il contributo più concreto del fix sprint alla deliverability.

```bash
pip install -r backend/config/requirements.txt
pip install -r backend/config/requirements-dev.txt
pytest                     # 3 189 test, nessun PYTHONPATH da impostare
cd frontend && npm ci && npm run build
```

## Dipendenze esterne — dichiarate, non nascoste

Il §14 non pretende che i servizi esterni siano sempre disponibili; pretende che
la dipendenza sia **esplicita**. Lo è:

| Dipendenza | Come è dichiarata |
|---|---|
| `data_cache/document_grounding` | `POST /runs` in LIVE risponde **503** con il reason code `CACHE_PATH_NOT_FOUND` e il nome della variabile da configurare |
| `OLLAMA_API_KEY` | `llm_config.resolve_endpoint()` solleva `MissingLLMCredentials`, esposto come 503 |
| gold set clinico | gitignored per riservatezza, con manifest e hash tracciati |
| rete NCBI (RQ2) | `run_rq2.py` supporta `--offline`; `ncbi_requests` registrato nell'artifact |

Nessuna di queste degrada silenziosamente.

## Cosa resta non riproducibile

1. **LIVE end-to-end** — richiede la cache documentale (testo di terzi, non
   redistribuibile) e una credenziale segreta. `REPRODUCIBLE_WITH_EXTERNAL_DEPENDENCY`.
2. **Rilevanza semantica dei PMID (RQ2)** — `NOT_MEASURED` per progetto:
   richiede annotazione umana. Dichiarato, non rivendicato.
3. **Fedeltà semantica v3 contro giudizio esperto** — il campione manuale a 70
   record ha le colonne del revisore vuote (ISS-011).
4. **Type checking del backend** — nessuna configurazione versionata.
5. **`npm run lint`** — fallisce con 36 errori preesistenti (NEW-02).

Le prime tre sono limiti scientifici dichiarati, non difetti software.

## Verdetto

`reproducible_from_clean_repository = true` per il **nucleo** del progetto:
ambiente, dati, test, build, runtime in REPLAY, esperimenti e metriche.

La qualificazione è necessaria e va scritta nella tesi: LIVE non è riproducibile
da un clone pulito, e la ragione è documentata nel codice stesso.
