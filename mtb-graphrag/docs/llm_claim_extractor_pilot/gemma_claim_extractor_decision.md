# Decisione finale sul Claim Extractor

Applicazione dell'interpretazione a cascata (sezione 17 del protocollo):
sicurezza -> trasporto -> stabilità -> utilità.

1. **Sicurezza**: zero hard stop nei due checkpoint. Zero quote inesistenti
   accettate, zero SourceUnit inventate, zero campi graph-only accettati,
   zero CONTRADICTED promosso a positivo, validatore invariato — non è
   `CLAIM_EXTRACTOR_SAFETY_FAILURE`.
2. **Trasporto**: transport success run 1 = 88%, run 2 = 80%. Entrambi
   sotto la soglia richiesta del 90% —> **`CLAIM_EXTRACTOR_TRANSPORT_INSUFFICIENT`**.

La decisione si ferma qui per costruzione (il criterio D ha priorità sulla
valutazione di stabilità/utilità una volta che il trasporto è insufficiente
su almeno una run). Va però segnalato, per completezza, che anche
proseguendo l'analisi la soglia di stabilità sui valori non sarebbe stata
raggiunta: `normalized_value_agreement_active_rate`=19.0% (soglia 85%) e
`direction_agreement_rate`=42.9% (soglia 80%) sono entrambe ampiamente
sotto soglia — sebbene, come discusso in `gemma_run1_run2_stability.md`,
questo rifletta soprattutto l'alto numero di tentativi che restano
`SAME_AMBIGUITY` (nessun valore validato da nessuna delle due parti) più
che veri disaccordi di valore (`VALUE_DISAGREEMENT`=0,
`DIRECTION_DISAGREEMENT`=0 su tutti i 100 slot).

## Decisione

**CLAIM_EXTRACTOR_TRANSPORT_INSUFFICIENT**

## Raccomandazione architetturale

Il collo di bottiglia del sistema non è più — a differenza di MiniMax — il
grounding semantico (zero violazioni di sicurezza in 150 chiamate totali
tra Stadio 1 e Stadio 2, alto accordo su status/esito quando il transport
funziona), ma l'affidabilità del meccanismo di tool-calling di
`gemma4:cloud` anche con `tool_choice` forzato via endpoint
OpenAI-compatible: il tasso di successo oscilla 68% (nativo) -> 96%
(riconciliato Stadio 1) -> 88%/80% (Stadio 2, forced-tool puro, senza il
beneficio della selezione post-hoc del trasporto che aveva innalzato il
96% nello Stadio 1). Prima di considerare Gemma idoneo per il pilot
completo, servirebbe indagare la causa dei `FORCED_TOOL_IGNORED`/
`TEXT_RESPONSE` residui (possibile correlazione con lunghezza/complessità
del bundle, non ancora analizzata) piuttosto che ripetere ulteriori run
identiche. Il segnale di utilità è reale ma marginale (1 campo
ripetutamente validato su 100 slot): anche risolvendo il trasporto, non ci
si aspetterebbe un salto qualitativo di resa informativa, solo una
misura più completa di quella già osservata.
