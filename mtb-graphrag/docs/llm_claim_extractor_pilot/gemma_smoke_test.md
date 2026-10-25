# Smoke test Gemma (3 chiamate)

Stesso protocollo di MiniMax: transport `TOOL_CALL_FLAT/1.2`, prompt
`1.3`, schema `1.0`, validator `deterministic-llm-proposal-validator/1.1`,
stessi 3 EvidenceBundle, `run_index` 0/1/2, `seed=run_index`. Cache documenti
riusata invariata dal pilot MiniMax (stesso worktree, stessi file
`data_cache/document_grounding/pubmed|pmc`), nessun nuovo documento
recuperato.

## A. DIRECT — EB-b4c48ba003913f278ff182a6

Transport `TOOL_CALL_VALID`, validator `ACCEPTED`. Tutti e 4 i campi
(disease, biomarker, intervention, direction) accettati con quote letterali
e SourceUnit reali del bundle. `final_support_status = DIRECT`, coerente con
l'etichetta attesa. Nessuna contraddizione rilevata. Direzione conservata.

## B. PARTIAL — EB-2ae853e8abf1195cc4c84846

Transport `TOOL_CALL_VALID` con un drop dell'adapter
(`biomarker:DROPPED_AMBIGUOUS_OFFSET`, quote non univoca nel testo).
Validator: `disease` e `intervention` accettati; `biomarker` scartato come
`DROPPED_GRAPH_ONLY` (valore non ancorato al testo, correttamente non
accettato — nessun campo copiato dalla candidate è passato); `direction`
scartato per `DROPPED_DIRECTION_CONFLICT`. Esito validator
`REJECTED_DIRECTION` (il conflitto di direzione fa fallire l'intera
proposta anche se due campi erano grounded). `final_support_status` non
calcolato (atteso: il validator non ha raggiunto un esito accettabile).
Nessun campo mancante è stato inventato; nessuna contraddizione fabbricata.

## C. CONTRADICTED — EB-6a291f12975b20b79e1c3dd7

Transport `TOOL_CALL_VALID`, validator `ABSTAINED`: il modello dichiara
esplicitamente (in `abstention_reason`) che il testo non menziona
l'intervento richiesto dalla candidate (`INFIGRATINIB`, presente solo
`BGJ398`) né lega il biomarker alla malattia esatta della candidate. Il
modello non adatta il documento alla candidate e non produce evidenza
positiva. `final_support_status = AMBIGUOUS` (via `ClaimSupportVerifier`,
nessun campo validato) — il caso CONTRADICTED non è promosso a supporto
positivo.

## Riepilogo numerico

| Metrica | Valore |
|---|---|
| Chiamate reali eseguite | 3 |
| Transport validi | 3/3 |
| Proposte che raggiungono il validator | 3/3 |
| Validator `ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS` | 1/3 |
| Quote inesistenti accettate | 0 |
| SourceUnit inventate accettate | 0 |
| Campi graph-only accettati | 0 |
| Candidate leakage nei campi accettati | 0 |
| CONTRADICTED promosso | No |
| `think=False` onorato | 3/3 |
