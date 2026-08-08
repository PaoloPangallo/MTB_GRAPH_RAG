# Come abilitare una run LIVE

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. Ricostruire la cache

Una sola volta per ambiente. Richiede rete verso NCBI E-utilities, PMC OAI e
ClinicalTrials.gov.

```powershell
python scripts/bootstrap_research_document_cache.py
```

Recupera i 40 documenti del closed set (~2.1 MB, ~1 minuto) e li scrive in
`data_cache/document_grounding`. È idempotente: rilanciarlo su una cache
completa non produce alcuna richiesta di rete.

Opzioni utili:

| Opzione | Effetto |
|---|---|
| `--audit-only` | Solo inventario del manifest, nessuna rete |
| `--force` | Riscarica anche i payload già presenti |
| `--probe-baseline-unavailable` | Verifica se i 3 documenti storicamente non risolti lo siano ancora |
| `--only <document_id>` | Limita a documenti specifici (ripetibile) |
| `--delay-seconds` | Pausa fra richieste (default `0.34`, ≈3 req/s) |

## 2. Verificare

```powershell
python scripts/verify_research_document_cache.py
```

Sola lettura, nessuna rete. Attesi:

```
validate_cache      : True []
documenti parsati   : 40
SourceUnit ricostr. : 3402 (con testo 3402)
intersezione        : 3402
mancanti            : 0
nuovi               : 0
bundle con testo    : 25/25  (unita 76/76)
```

`mancanti` o `nuovi` diversi da zero significano che il testo estratto non
corrisponde più all'indice congelato: **non usare la cache in LIVE** senza prima
analizzare il drift. Vedi [06_drift_analysis.md](06_drift_analysis.md).

## 3. Configurazione

Se la cache sta nella posizione predefinita — `<repo>/data_cache/document_grounding` —
**non serve alcuna variabile**. Il default è relativo alla radice dei dati e
funziona da qualunque directory si avvii il backend.

Solo se la cache sta altrove:

```
RESEARCH_DOCUMENT_CACHE_PATH=<percorso assoluto>
```

Il percorso deve essere **assoluto**: `cache_path()` esegue
`Path(value).resolve()`, quindi un percorso relativo verrebbe risolto sulla
directory di lavoro del processo — esattamente il difetto che questa variabile è
nata per eliminare. `RESEARCH_PIPELINE_CACHE_ROOT` resta accettata come alias
storico; `DOCUMENT_GROUNDING_CACHE` non ha alcun effetto sul runtime.

Serve inoltre il flag del research runtime, che `run.ps1` imposta già:

```
VERIFIABLE_PIPELINE_RESEARCH_ENABLED=1
```

Il backend va riavviato dopo ogni cambio di configurazione.

## 4. Avviare

```powershell
.\run.ps1
```

Console su `/research/verifiable-pipeline`.

## 5. Verificare che il warning sia sparito

```powershell
curl http://localhost:8000/api/v1/research/pipeline/config
```

Atteso:

```json
{"document_cache": {"document_cache_available": true, "document_count": 40,
                    "documents_with_text": 40, "reason_codes": []},
 "execution_modes": {"live_available": true, "live_unavailable_reason": null}}
```

Con `live_available: true` il pannello di input non mostra più l'avviso sulla
cache, e la modalità LIVE diventa selezionabile.

## 6. Cosa serve ancora, oltre alla cache

Una run LIVE chiama davvero il modello. Occorre quindi un endpoint LLM
raggiungibile e credenziali configurate (`OLLAMA_BASE_URL`, `OLLAMA_API_KEY`,
oppure `RESEARCH_PIPELINE_LLM_BASE_URL` per un override di run). Senza,
`POST /runs` in LIVE risponde `503` con `MissingLLMCredentials` — un rifiuto
esplicito, non un ripiego su REPLAY.
