# EvidenceStatement atomicity options

| Opzione | Statement simulati | Vantaggio | Rischio |
| --- | ---: | --- | --- |
| A — lista | 147 | migrazione semplice | perde la relazione intervento-direzione |
| B — atomico | 147 | claim therapy-level | perde un parent condiviso |
| C — parent + child | 147 | provenance condivisa | maggiore complessità e link da rivalutare |

La simulazione sicura non atomizza i gruppi irrisolti. Il massimo non revisionato
di 162 statement è riportato
soltanto come limite superiore proibito.

## Strategia ID valutata

`ES-V3-<sha256(graph_evidence_id|canonical_intervention|direction|assertion_polarity)[:20]>`. Non è implementata. La tupla
canonica completa resta il collision guard e conserva il graph evidence ID.

## Raccomandazione

keep every multi-intervention graph record parent-only until source review; if attribution is confirmed, option C best preserves graph identity and claim-level atomicity
