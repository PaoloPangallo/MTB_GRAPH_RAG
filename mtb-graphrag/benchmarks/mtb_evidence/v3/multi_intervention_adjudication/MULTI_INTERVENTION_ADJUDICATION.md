# Adjudication dei gruppi multi-intervento

`adjudicator_role = author_adjudicator`, `adjudication_independence = non_independent`

L'adjudication e' stata eseguita dall'autore sugli stessi artefatti che ha prodotto.
Non e' una revisione esterna e non viene dichiarata tale. Nulla diventa gold clinico:
`propagation_policy = prototype_only`, `hard_filterable = false`,
`final_clinical_gold = false`.

## La decisione che veniva prima di tutte

`parent_is_provenance_container`. Il parent conserva provenienza e identita' e smette di
essere una proposizione terapeutica. Il razionale sta in `PARENT_SEMANTICS_DECISION.md`;
in breve, quattro claim del corpus attuale non sono sostenuti dalla fonte e nascono da una
scelta dell'adapter — promuovere il primo valore scalare di un campo multi-intervento —
che non e' un giudizio documentale.

## Esito

- claim approvati: 15 (9 atomici, 3 aggregati, 3 di regime)
- associazioni non sostenute: 6
- associazioni non risolte: 6
- gruppi che non producono alcun claim: 2 (`evidence:3811`, `evidence:4759`)

| gruppo | prima review | replica | adjudicata | claim |
| --- | --- | --- | --- | --- |
| `evidence:11240` | `combination_regimen_required` | `mixed_parent_and_children` | `mixed_claim_structure_approved` | 2 |
| `evidence:12131` | `combination_regimen_required` | `combination_regimen_required` | `regimen_claim_approved` | 1 |
| `evidence:12156` | `combination_regimen_required` | `combination_regimen_required` | `regimen_claim_approved` | 1 |
| `evidence:1483` | `should_not_materialize_missing_interventions` | `should_not_materialize_missing_interventions` | `atomic_children_approved` | 1 |
| `evidence:1484` | `should_not_materialize_missing_interventions` | `should_not_materialize_missing_interventions` | `atomic_children_approved` | 1 |
| `evidence:1851` | `aggregate_parent_only` | `aggregate_parent_only` | `aggregate_claim_approved` | 1 |
| `evidence:1853` | `aggregate_parent_only` | `aggregate_parent_only` | `aggregate_claim_approved` | 1 |
| `evidence:229` | `atomic_children_supported` | `atomic_children_supported` | `atomic_children_approved` | 2 |
| `evidence:275` | `aggregate_parent_only` | `aggregate_parent_only` | `aggregate_claim_approved` | 1 |
| `evidence:296` | `atomic_children_supported` | `atomic_children_supported` | `atomic_children_approved` | 2 |
| `evidence:3811` | `insufficient_for_atomicity_decision` | `insufficient_for_atomicity_decision` | `unresolved_deferred` | 0 |
| `evidence:4759` | `aggregate_parent_only` | `aggregate_parent_only` | `unsupported_associations_rejected` | 0 |
| `evidence:841` | `mixed_parent_and_children` | `mixed_parent_and_children` | `atomic_children_approved` | 2 |

## I due casi concordanti

Erano il vero motivo per cui questa fase non poteva limitarsi ai disaccordi.

**`evidence:275`** — ne' `erlotinib` ne' `gefitinib` compaiono nella fonte: la coorte e'
descritta solo come trattata con EGFR-TKI. L'attribuzione specifica e' rifiutata e
sostituita da un claim aggregato di classe. E' l'unico caso in cui l'adjudication toglie
una proposizione terapeutica gia' presente nel corpus.

**`evidence:4759`** — l'unico esito della fonte riguarda le mutazioni EGFR *non comuni*;
L858R ed ex19del compaiono solo come conteggi di prevalenza. Il claim e' rifiutato e
nessun sostituto viene creato: costruirne uno sulle mutazioni non comuni significherebbe
cambiare il biomarcatore senza dirlo.

Su entrambi le due revisioni erano d'accordo su ogni asse dell'intervento. La concordanza
non era una prova di correttezza, e nessuna metrica di accordo poteva rilevarlo.

## Regime contro misto

`evidence:11240` era l'unico disaccordo group-level. Approvati **entrambi** i claim: un
regime per [erlotinib, ramucirumab] sull'unita' del braccio sperimentale, e un claim
atomico per erlotinib sull'unita' del braccio di controllo, dove e' l'unico agente attivo
e ha un esito con intervallo di confidenza. Il risultato del regime non viene propagato ai
componenti: il claim atomico poggia su un'altra unita' documentale, e il test lo verifica.

## Mapping pending

2 interventi restano non materializzabili: `infigratinib`, `luminespib`.
Nel claim aggregato dei due gruppi FGFR2 i membri restano i termini letterali della fonte,
`BGJ398` e `PD173074`: il codice di sviluppo non viene canonicalizzato nel nome generico
nemmeno dentro l'ID, perche' l'ID renderebbe stabile un'equivalenza non verificata.

## Simulazione, senza toccare il corpus

- statement operativi correnti: 147
- statement da sostituire: 13
- statement da deprecare senza sostituto: 2
- claim risultanti: 149
- qualification link da rigenerare: 15
- view da rigenerare: 13

Nessuna metrica di retrieval e' stata calcolata e il gold non ha guidato alcuna decisione:
e' stato contato come inventario dopo che le decisioni erano chiuse.
