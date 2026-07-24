# Correction readiness

## Stati

| Stato | Valore | Motivo |
|---|---|---|
| `root_causes_identified` | `true` | tutti i 95 record mancanti e gli 84 query/graph-ID unici hanno una causa primaria |
| `technical_bug_fix_ready` | `true` | il comportamento gene-OR-alteration è riproducibile senza gold |
| `normalization_fix_ready` | `false` | disease alias e decorazioni dell'alterazione richiedono un contratto versionato |
| `corpus_regeneration_required` | `true` | serve per rappresentare senza perdita le 11 righe multi-intervento |
| `semantic_review_required` | `true` | equivalenze disease e granularità devono essere revisionate |
| `ready_to_restore_v2_coverage` | `false` | parte della differenza è architetturale e non deve essere forzata |
| `ready_to_rerun_exploratory_evaluation` | `false` | prima va deciso e applicato il perimetro delle correzioni |

## Correzioni classificate

1. `CCR-001` — `implementation_bug_fix`: rendere gene e alterazione richiesti
   dimensioni congiuntive. È dimostrabile senza gold, ma non è stata applicata
   in questa fase di audit.
2. `CCR-002` — `requires_domain_review`: introdurre, soltanto se approvata, una
   mappatura versionata fra le forme NSCLC. Nessun sinonimo runtime è stato
   aggiunto.
3. `CCR-003` — `adapter_regeneration_required`: preservare tutti gli interventi
   o materializzare statement distinti con identità esplicita.
4. `CCR-004` — `expected_architectural_difference`: non indebolire i filtri
   nativi per riprodurre traversal V2 per farmaco o fonte.
5. `CCR-005` — `should_not_fix`: non equiparare iCCA, cholangiocarcinoma e
   cholangiolocellular carcinoma senza ontologia e revisione.

Nessuna correzione è stata applicata. Retriever, scoring e corpus restano
byte-identici allo stato congelato.
