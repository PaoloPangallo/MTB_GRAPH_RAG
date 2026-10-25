# Screenshot della rotta `/research/verifiable-pipeline`

Sottoinsieme rappresentativo, prodotto da `scripts/e2e_supervisor_ui.py` contro
backend e frontend reali, senza mock. Lo script ne genera 62 — uno per stage,
per tab e per caso; qui restano i quattordici che coprono i passaggi centrali.

Per rigenerare l'insieme completo:

```
VERIFIABLE_PIPELINE_RESEARCH_ENABLED=1 CORS_ORIGINS="http://localhost:5180" \
  python -m uvicorn backend.api.main:app --port 8001

VITE_API_BASE_URL=http://localhost:8001 npx vite --port 5180

python scripts/e2e_supervisor_ui.py
```

| File | Cosa mostra |
|---|---|
| `00-home-redirect.png` | la radice apre la pipeline verificabile, non la vista storica |
| `00-legacy-route.png` | `/legacy/v3-deterministic` con la striscia `LEGACY V3 DETERMINISTIC` |
| `therapy-evaluation-strong-match--01-run.png` | i 15 stage con producer, durata e badge di replay |
| `…--stage-casecontext-parser.png` | il CaseContext estratto dal modello, prima della normalizzazione |
| `…--stage-casecontext-match.png` | confronto campo per campo, con testo di supporto e offset |
| `…--stage-source-unit.png` | locatori, sezione e `content_hash`; nessun testo del documento |
| `…--stage-paper-context-enricher.png` | decisione QUOTE, citazione, modello, prompt e transport version |
| `…--stage-quote-validation.png` | `ENRICHMENT_V2_ACCEPTED` e ammissione al dossier |
| `…--stage-deterministic-gates.png` | tabella dei controlli con la colonna dell'origine |
| `…--tab-dossier.png` | le tre sezioni: evidenza deterministica, author context, limitazioni |
| `…--tab-provenienza.png` | la catena completa, da CaseContext a voce di dossier |
| `contradicted-or-resistance--stage-paper-context-enricher.png` | ABSTAIN su un caso di resistenza |
| `contradicted-or-resistance--tab-provenienza.png` | `PARENT_LEVEL_ONLY`: candidate non ancorata a un documento |
| `casecontext-mismatch-no-match--01-run.png` | arresto corretto; stage a valle non eseguiti, con il motivo |
