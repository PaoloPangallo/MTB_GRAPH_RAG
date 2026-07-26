# Regimi, aggregati e classi

Sono i tre modi in cui una fonte puo' parlare di piu' di un farmaco insieme, e nessuno
dei tre autorizza a parlare di uno solo.

## Regime

Il risultato appartiene alla combinazione. Exact match solo quando l'insieme dei
componenti della query coincide con quello del claim dopo normalizzazione verificata;
l'ordine non conta, perche' il confronto e' fra insiemi.

- **componente singolo** → `regimen_component_related`, warning
  `RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT`, mai exact e mai primario.
- **sottoinsieme proprio** → `regimen_subset_mismatch`, `QUERY_REGIMEN_IS_PROPER_SUBSET`.
- **sovrainsieme proprio** → `regimen_superset_mismatch`, `QUERY_REGIMEN_IS_PROPER_SUPERSET`.

La scelta fra warning e audit per i correlati e' warning: il claim e' pertinente e
l'utente ha diritto di vederlo, purche' non sia presentato come supporto per il
componente. Nasconderlo in audit perderebbe informazione utile; metterlo nel primario
direbbe una cosa falsa.

## Aggregato di classe

Exact solo su stessa classe canonica o alias di classe verificato. Una relazione
verificata `farmaco appartiene a classe` produce `class_member_related` con warning
`CLASS_LEVEL_EVIDENCE_NOT_DRUG_SPECIFIC`, mai `exact_intervention`.

Il registro delle appartenenze verificate e' oggi **vuoto di proposito**. Senza una voce
approvata, `erlotinib appartiene a EGFR-TKI` resta `unresolved_class_relation` e finisce
in audit. Dedurre l'appartenenza dalla somiglianza delle stringhe sarebbe la stessa
inferenza che l'adjudication ha rifiutato in `evidence:275`, spostata di un livello.

## Aggregato non separabile

La presenza del farmaco nella lista non autorizza un claim atomico:
`aggregate_member_related`, warning `AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION`.

## Mapping pending

`BGJ398` e `infigratinib` non sono lo stesso termine finche' il mapping non e' approvato.
Una query su `infigratinib` contro l'aggregato che nomina `BGJ398` da'
`mapping_pending` e finisce in audit, non in warning: la differenza non e' di forza
dell'evidenza ma di identita' dell'intervento.

## Casi osservati nella simulazione

| query | claim | match | bucket |
| --- | --- | --- | --- |
| `Q02` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `audit_only_results` |
| `Q03` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q03` | `CLM-ac64c0e56246f6ea29ca` | `regimen_component_related` | `retained_with_warning` |
| `Q04` | `CLM-ac64c0e56246f6ea29ca` | `exact_regimen` | `primary_ranked_results` |
| `Q05` | `CLM-5ce49705979f72f174e9` | `regimen_subset_mismatch` | `retained_with_warning` |
| `Q06` | `CLM-4a89bb28592af7ebaccf` | `regimen_superset_mismatch` | `retained_with_warning` |
| `Q07` | `CLM-4ffe85304f3ef5533b58` | `exact_intervention_class` | `primary_ranked_results` |
| `Q08` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `audit_only_results` |
| `Q08` | `CLM-ac64c0e56246f6ea29ca` | `regimen_component_related` | `rejected_by_native_constraints` |
| `Q09` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q09` | `CLM-a7c903cf8d423f015e29` | `aggregate_member_related` | `retained_with_warning` |
| `Q09` | `CLM-aae818bbc8ec735a255d` | `aggregate_member_related` | `rejected_by_native_constraints` |
| `Q10` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q10` | `CLM-a7c903cf8d423f015e29` | `mapping_pending` | `audit_only_results` |
| `Q10` | `CLM-aae818bbc8ec735a255d` | `mapping_pending` | `rejected_by_native_constraints` |
| `Q11` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q11` | `CLM-ac64c0e56246f6ea29ca` | `regimen_component_related` | `retained_with_warning` |
| `Q12` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q12` | `CLM-ac64c0e56246f6ea29ca` | `regimen_component_related` | `rejected_by_native_constraints` |
| `Q13` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q14` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q15` | `CLM-4ffe85304f3ef5533b58` | `unresolved_class_relation` | `rejected_by_native_constraints` |
| `Q15` | `CLM-ac64c0e56246f6ea29ca` | `regimen_component_related` | `retained_with_warning` |
| `Q16` | `CLM-4a89bb28592af7ebaccf` | `exact_regimen` | `primary_ranked_results` |
