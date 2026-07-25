# Confronto fra prima revisione e replica cieca

`comparison_type = first_review_vs_blinded_non_independent_replicate`

La replica non e' indipendente: il prompt che l'ha commissionata nominava la
raccomandazione della prima revisione e il contesto di sessione conteneva gli oggetti
dei suoi commit. Ogni numero di questa pagina e' descrittivo. In particolare
`independent_inter_reviewer_agreement = false` e
`valid_for_external_reliability_claim = false`: un accordo elevato qui non e' una
convergenza fra revisori nel senso usuale, ed e' compatibile con l'ipotesi che le due
letture condividano un'origine. Serve a preparare l'adjudication e ad affinare le linee
guida, non a validare nulla.

## Perimetro

- 13 gruppi, allineati per `(graph_evidence_id, source_id)`
- 28 associazioni, allineate per `(graph_evidence_id, source_id, intervento normalizzato)`
- allineamento per chiave, mai per posizione; nessuna asimmetria
- i codici di sviluppo restano distinti dai nomi generici: `BGJ398` non e' `infigratinib`,
  `AUY922` non e' `luminespib`

## Intervention-level

- `compatible_agreement`: 3
- `documentary_role_disagreement`: 4
- `exact_agreement`: 16
- `materialization_disagreement`: 5

Accordo sulla classificazione: 21/28 (75.0%).
Accordo sull'esito del claim: 23/28 (82.1%).

## Group-level

Accordo esatto: 12/13 (92.3%).

| gruppo | prima revisione | replica | accordo |
| --- | --- | --- | --- |
| `evidence:11240` | `combination_regimen_required` | `mixed_parent_and_children` | **no** |
| `evidence:12131` | `combination_regimen_required` | `combination_regimen_required` | si |
| `evidence:12156` | `combination_regimen_required` | `combination_regimen_required` | si |
| `evidence:1483` | `should_not_materialize_missing_interventions` | `should_not_materialize_missing_interventions` | si |
| `evidence:1484` | `should_not_materialize_missing_interventions` | `should_not_materialize_missing_interventions` | si |
| `evidence:1851` | `aggregate_parent_only` | `aggregate_parent_only` | si |
| `evidence:1853` | `aggregate_parent_only` | `aggregate_parent_only` | si |
| `evidence:229` | `atomic_children_supported` | `atomic_children_supported` | si |
| `evidence:275` | `aggregate_parent_only` | `aggregate_parent_only` | si |
| `evidence:296` | `atomic_children_supported` | `atomic_children_supported` | si |
| `evidence:3811` | `insufficient_for_atomicity_decision` | `insufficient_for_atomicity_decision` | si |
| `evidence:4759` | `aggregate_parent_only` | `aggregate_parent_only` | si |
| `evidence:841` | `mixed_parent_and_children` | `mixed_parent_and_children` | si |

### Matrice di confusione group-level

Righe: prima revisione. Colonne: replica.

| | `aggregate_parent_only` | `atomic_children_supported` | `combination_regimen_required` | `insufficient_for_atomicity_decision` | `mixed_parent_and_children` | `should_not_materialize_missing_interventions` |
| --- | --- | --- | --- | --- | --- | --- |
| `aggregate_parent_only` | 4 | 0 | 0 | 0 | 0 | 0 |
| `atomic_children_supported` | 0 | 2 | 0 | 0 | 0 | 0 |
| `combination_regimen_required` | 0 | 0 | 2 | 0 | 1 | 0 |
| `insufficient_for_atomicity_decision` | 0 | 0 | 0 | 1 | 0 | 0 |
| `mixed_parent_and_children` | 0 | 0 | 0 | 0 | 1 | 0 |
| `should_not_materialize_missing_interventions` | 0 | 0 | 0 | 0 | 0 | 2 |

## Kappa, e perche' non va letto

- group-level: 0.9044 (n=13, categorie=6, cella attesa minima=0.077)
- classificazione intervention-level: 0.6859 (n=28, categorie=8, cella attesa minima=0.0)
- esito del claim: 0.7266

I tre valori sono calcolati e nessuno dei tre e' interpretabile. Due ragioni
indipendenti: le codifiche non sono indipendenti, quindi kappa non misura quello per cui
esiste; e con 13 e 28 item su sei-otto categorie piu' celle attese restano sotto 5, quindi
il valore oscilla con la prevalenza. Sono riportati per completezza, non come risultato.

## Locator e unita' documentali

- accordo di granularita' del locator: 13/28 (46.4%)
- locator a livello di unita' interna: prima 13/28, replica 28/28
- unita' documentali distinte: prima 11, replica 18
- accordo sulla segmentazione dentro il gruppo: 17/28

La differenza sulle unita' e' soprattutto nello spazio degli identificatori: la prima
revisione ne usa uno per fonte, ma il campo `documentary_unit` distingue in prosa braccio,
paziente e modello. L'eccezione e' `evidence:841`, dove le due revisioni ancorano lo stesso
claim a due eventi clinici diversi pur restando in accordo su tutto il resto.

## Consenso provvisorio

Gruppi che soddisfano tutti i criteri: 1/13.

Il criterio e' congiuntivo e severo: stessa decisione, verdetti intervention-level tutti in
accordo, locator sufficienti in entrambe, nessun mapping pending, nessun rischio
aggregate-to-specific, nessun problema di scope. Basta un elemento perche' il gruppo vada
comunque all'adjudicator. Il consenso resta `prototype_only`: non finale, non
hard-filterable, non validato in modo indipendente.
