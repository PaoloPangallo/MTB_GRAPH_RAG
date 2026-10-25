# Confronto MiniMax vs Gemma

Stessi 3 EvidenceBundle, stesso transport/prompt/schema/validator per
entrambi i modelli.

| Metrica | MiniMax (minimax-m3:cloud) | Gemma (gemma4:cloud) |
|---|---|---|
| Transport validi | 2/3 | 3/3 |
| Proposte che raggiungono il validator (semantic_reached) | 2/3 | 3/3 |
| Validator `ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS` | 0/3 | 1/3 |
| `final_support_status` calcolato (non nullo) | 0/3 | 2/3 (DIRECT, AMBIGUOUS) |
| Quote inesistenti accettate | 0 | 0 |
| SourceUnit inventate accettate | 0 | 0 |
| Campi graph-only accettati | 0 | 0 |
| Errori di direzione (drop/conflict) | 1 (bundle CONTRADICTED) | 2 (bundle PARTIAL e CONTRADICTED, entrambi correttamente scartati) |
| Negazione rilevata correttamente | n/a (nessun campo validato) | n/a (nessun campo con negazione nei 3 casi) |
| CONTRADICTED preservato (non promosso) | Sì | Sì |
| DIRECT preservato | No (transport `INVALID_TOOL_ARGUMENTS` su questo bundle) | Sì (`ACCEPTED`, tutti i 4 campi, `final_support_status=DIRECT`) |
| Comportamento thinking (`think=False` onorato) | No, 3/3 (thinking_length 3647–13042 caratteri) | Sì, 3/3 (thinking_length 0) |
| Token output (per chiamata) | 1883 / 3919 / 3151 | 444 / 542 / 388 |
| Latenza (ms, per chiamata) | 11962.7 / 26460.2 / 21372.3 | 2619.9 / 3053.5 / 6089.95 |

## Lettura

Gemma supera MiniMax su ogni asse misurato: transport interamente valido
(3/3 vs 2/3), nessuna chiamata persa per schema del tool-call malformato,
un caso `ACCEPTED` pulito con `DIRECT` preservato (MiniMax non ne ha
prodotto nessuno), rispetto effettivo di `think=False`, output più
compatto e latenza nettamente inferiore. Su nessuno dei due modelli sono
state accettate quote inesistenti, SourceUnit inventate o campi
graph-only — il validatore ha filtrato correttamente in entrambi i casi.

Gemma non raggiunge tuttavia la soglia di validità del protocollo che
richiede almeno 2/3 proposte `ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS`
(ottenuto: 1/3, sul bundle PARTIAL il conflitto di direzione fa fallire
l'intera proposta). Vedi `gemma_model_decision.md`.
