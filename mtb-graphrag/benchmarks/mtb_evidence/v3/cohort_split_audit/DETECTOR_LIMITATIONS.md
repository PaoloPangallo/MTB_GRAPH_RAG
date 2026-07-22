# Limiti del rilevatore di split

## Il rilevatore in produzione

`requires_cohort_split` decide confrontando **interventi e malattie fra gli
statement** di una fonte. Non legge il testo della fonte.

Da questo discendono i suoi limiti, e non sono di configurazione ma di forma:

| Puo' rilevare | Non puo' rilevare |
| --- | --- |
| fonti con piu' statement che divergono | fonti con un solo statement |
| divergenze su intervento o malattia | coorti diverse sotto lo stesso intervento |
| | evidenza clinica e preclinica mescolate |
| | sottogruppi e analisi secondarie |

## Il fallimento dimostrato

`PU-PMID-22277784-cohort-1` ha **10 statement** ed e'
stata classificata `insufficient_source_information`.

La struttura reale, confermata leggendo la fonte: una coorte clinica di 18 pazienti piu' tre pannelli su cellule Ba/F3, confermati dalla revisione della fonte.

i dieci statement concordavano abbastanza da non produrre divergenza, e il segnale strutturale vive nel full text, che il rilevatore non legge. Il fallimento non e' dovuto al numero di statement.

Il punto e' questo: prima di quella revisione si pensava che il buco riguardasse
le fonti a statement singolo. Il caso mostra che riguarda **il canale del
segnale**. Dieci statement non sono bastati, perche' il segnale non stava li'.

## Il rilevatore proposto

`assess_split` legge la fonte e riporta i segnali insieme al verdetto.

- 32 pattern in 10 categorie
- verdetti: `split_not_indicated`, `split_possible`, `split_likely`, `split_required`, `insufficient_information`
- deterministico, nessun modello linguistico coinvolto
- **indipendente dal numero di statement**
- il titolo da solo non basta mai

Riporta i segnali con i loro span perche' un verdetto senza prove non e'
auditabile: chi legge deve poter contestare la conclusione guardando il testo
che l'ha prodotta.

### Non promosso in produzione

non promosso in produzione in questa fase: va prima validato contro revisioni umane, che oggi esistono su una sola fonte.

C'e' anche una ragione di merito: il rilevatore proposto e' tarato su un solo
caso confermato. Promuoverlo adesso significherebbe generalizzare da un esempio.

## La regola che ne discende

L'audit ha applicato a se stesso la lezione: una fonte senza segnali **nel solo
abstract** non viene piu' classificata `single_propagatable_unit`, ma
`insufficient_source_information`. L'assenza di informazione non e' informazione
di assenza, e su questa fonte specifica lo abbiamo verificato.

## Esposizione residua

73 unita' su 102 hanno un solo statement
(71.6%). Per il rilevatore in
produzione sono invisibili per costruzione.

## Guardie

12 regole eseguibili con errore tipizzato:

- `clinical_population_to_model`
- `clinical_dimensions_to_model`
- `preclinical_setting_to_patients`
- `model_comparator_to_patients`
- `cross_cohort_identity`
- `cross_arm_intervention`
- `subgroup_to_population`
- `relative_versus_complete_resistance`
- `in_vitro_to_clinical_benefit`
- `mapping_needs_provenance`
- `absence_is_not_evidence`
- `case_report_to_population`

Zero violazioni sugli artefatti attuali. Non significa che le regole siano
inerti: sono provate su casi deliberatamente scorretti nella suite, dove tutte
scattano.

