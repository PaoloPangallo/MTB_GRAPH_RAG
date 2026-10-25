# Transizioni BUNDLE+RULES -> BUNDLE+GEMMA+VALIDATORE

Confronto per ciascuno dei 25 bundle tra la baseline B (`support_status`
già registrato in `evidence_bundles.jsonl`, calcolato con le sole regole
deterministiche) e lo status finale prodotto da Gemma + validatore in
questo Stadio 1.

## Riepilogo

| Categoria | Conteggio |
|---|---:|
| Nuovi DIRECT | 0 |
| DIRECT persi | 0 |
| CONTRADICTED persi (promosso a positivo) | 0 |
| CONTRADICTED recuperati (nuovo CONTRADICTED dove la baseline non lo era) | 0 |
| PARTIAL -> DIRECT | 0 |
| AMBIGUOUS -> DIRECT | 0 |
| Astensioni | 8 |

## Lettura

Non si osservano transizioni di categoria in nessuna direzione in questo
campione. Il solo `DIRECT` presente (il bundle dello smoke test) resta
`DIRECT`; nessun altro bundle raggiunge `DIRECT`; il `PARTIAL`
`EB-42cb660f5be17914df59a8fc` resta `PARTIAL` (via
`ACCEPTED_WITH_DROPPED_FIELDS`, campi realmente supportati accettati, il
resto scartato); i due CONTRADICTED restano non promossi a supporto
positivo.

La ragione principale per cui non emergono nuovi `DIRECT`/`PARTIAL` non è
un errore sistematico di grounding, ma il tasso di fallimento del
transport (8/22 nuove chiamate senza tool-call valida) e i due rigetti
`REJECTED_CONTRADICTION` per negazione non preservata (vedi
`gemma_stage1_validation.md`): questi bundle non raggiungono mai il calcolo
dello status finale, quindi non possono generare una transizione. Nessun
campo è stato "recuperato solo da Gemma" oltre a quanto già accettato nei
casi `ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS` sopra descritti; tutti i
campi scartati lo sono stati per le regole deterministiche del validatore
(quota mancante, offset ambiguo, conflitto di direzione, valore
graph-only), non per errori del confronto.
