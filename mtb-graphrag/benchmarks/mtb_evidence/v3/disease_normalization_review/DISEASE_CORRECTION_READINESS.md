# Disease correction readiness

| Stato | Valore | Motivazione |
|---|---:|---|
| disease_root_causes_identified | true | Tutte le 109 righe e tutte le origini V2 sono classificate. |
| safe_normalization_fix_ready | true | L’alias NSCLC è già dichiarato e verificato localmente; nessun nuovo sinonimo è necessario. |
| ontology_aware_policy_ready | false | Le relazioni locali esistono, ma warning, scoring e semantica parent/child non sono ancora approvati. |
| broad_candidate_policy_ready | false | È definita e simulata, ma richiede una decisione esplicita sulla candidate generation. |
| V2_V3_hybrid_policy_ready | false | Il pool V2 include cross-gene, drug/source neighborhood e unità multi-intervento. |
| domain_review_required | true | Sibling, contesti generici e relazioni senza ID non possono essere risolti tecnicamente. |
| adapter_regeneration_required | true | La decisione multi-intervento resta separata e non è stata affrontata in questa fase. |
| ready_for_disease_fix_implementation | false | È pronto solo il sottoinsieme alias-safe; la policy disease complessiva non è scelta. |
| ready_for_full_exploratory_rerun | false | Servono decisione disease e decisione adapter multi-intervento. |

## Correzioni safe

È tecnicamente dimostrabile, senza gold, che il filtro può riconoscere gli alias
già presenti nel contratto e nel normalizzatore locale. Questo non autorizza
parent/child, sibling o sinonimi nuovi.

## Correzioni che richiedono review

- Supporto gerarchico iCCA/cholangiocarcinoma.
- Trattamento di `Cholangiolocellular Carcinoma`.
- Candidate generation broad-soft.
- Provider ibrido V2/V3.
- Contesti pan-cancer o privi di relazione locale.
- Serializzazione e rigenerazione dell’adapter multi-intervento.

Nessuna correzione è stata applicata. Il prossimo gate è una decisione tecnica
separata sulla policy disease, seguita dalla decisione sull’adapter
multi-intervento; soltanto dopo è sensato pianificare il rerun esplorativo.
