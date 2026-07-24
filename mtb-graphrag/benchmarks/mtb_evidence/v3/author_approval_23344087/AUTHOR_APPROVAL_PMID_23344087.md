# Approvazione della prima revisione — PMID 23344087

**Decisione: `approve_with_corrections`.** Approvata da Paolo Pangallo, autore
della tesi, con assistenza LLM nella preparazione documentale.

Terza e ultima fonte del batch clinico/preclinico.

---

## 1. Fonte

| | |
|---|---|
| PMID | `23344087` |
| PMC | *nessuno* |
| Titolo | *Heterogeneity of genetic changes associated with acquired crizotinib resistance in ALK-rearranged lung cancer* |
| Parent unit | `PU-PMID-23344087-cohort-1` |
| Disponibilità | **`abstract_only`** |
| Hash dell'abstract | `23bc0f21fcbfb22ce3902d1ca802e6a2607e4b63a45dd1507c3a5c1f3199d296` |
| Locator | **6/6 verificati**, `{"exact": 6}` |
| Statement | `ES-V2-evidence-765`, `ES-V2-evidence-767` |

Hash e locator sono stati confrontati con `source_access_verification.jsonl`
prima che qualunque record venisse scritto, insieme a `availability`,
`full_text_stored`, `pmc_id` e alla dichiarazione di Europe PMC.

---

## 2. Il limite abstract-only

```
full_text_publicly_available = false
europe_pmc_status            = subscription required
in_pmc                       = false
open_access                  = false
public_access_route          = none
figures_and_tables_observable = false
```

La revisione ha letto 1683 caratteri di abstract, quattro sezioni
(`BACKGROUND`, `METHODS`, `RESULTS`, `CONCLUSIONS`) e sei locator, tutti `exact`.
Nient'altro.

```
source_basis                             = abstract_only
structural_confidence                    = partial
full_text_verified                       = false
requires_full_text_or_independent_review = true
```

La dichiarazione di indisponibilità è conservata verbatim. Se un giorno il full
text diventasse accessibile, questo record dice che cosa era vero quando la
decisione è stata presa, e quindi perché era prudente.

Il controllo non è burocratico: `abstract_only` è la ragione per cui due delle
tre unità proposte non vengono attivate. Se l'artefatto dicesse `full_text`, la
prudenza registrata qui sarebbe ingiustificata, e lo script si ferma prima di
scrivere.

`source_basis` viaggia anche con **ogni voce di provenienza**, non solo con
l'unità: un valore estratto da un abstract e uno estratto da un full text non
sono la stessa asserzione, e la differenza deve restare leggibile alla
granularità del campo.

---

## 3. Decisione strutturale

```
author_decision                = approve_with_corrections
structural_decision            = audit_split_partially_supported
clinical_preclinical_split     = confirmed
audit_proposed_units           = 2
source_review_proposed_units   = 3
author_approved_active_units   = 2
parent_state                   = superseded_by_reviewed_restructure
```

Due cose diverse, che il termine «partially supported» rischia di far leggere
come una sola: lo split **è** sostenuto, la sua granularità no.

---

## 4. Perché lo split è confermato

L'abstract nomina esplicitamente entrambe le componenti, ed entrambe come lavoro
della fonte.

| Componente | Locator | Frase |
|---|---|---|
| clinica | `B-clin-cohort` | *«Tumor samples were derived from seven ALK-positive NSCLC patients who showed acquired resistance to crizotinib»* |
| preclinica | `B-pre-design` | *«In vitro cytotoxicity of crizotinib and ALK downstream signals were compared between crizotinib-naive and -resistant NSCLC cells»* |

È la differenza con PMID 31358542, dove il verdetto poggiava anch'esso su una
sola occorrenza di «in vitro» ma quella occorrenza era una citazione. Qui la
frase sta nei metodi dell'abstract e descrive un esperimento della fonte. Un
segnale solo, e questa volta genuino.

---

## 5. Perché tre unità non sono approvate

Le tre proposte source-checked erano:

| Proposta | Che cosa affermava |
|---|---|
| `PU-PMID-23344087-clinical-cohort` | i sette pazienti — sostenuta |
| `PU-PMID-23344087-patient-derived` | SNU-2535 contro H3122 CR1 come unità propria |
| `PU-PMID-23344087-engineered-clones` | i cloni mutanti come unità propria |

Le ultime due affermano una **separazione**. L'abstract nomina i tre componenti,
ma non dice su quale fondo cellulare i cloni siano costruiti, né se derivino da
SNU-2535, da H3122 CR1 o da altro. Sapere che i componenti esistono non basta per
sapere che cosa sono, né quanti sistemi distinti rappresentino.

Attivarle come due unità avrebbe attribuito a ciascuna una identità sperimentale
che la fonte non fornisce — e l'artefatto risultante sarebbe stato
indistinguibile da uno prodotto leggendo il full text.

**Le proposte non sono dichiarate false.** Restano nello storico come ipotesi
strutturali plausibili che l'abstract non permette né di confermare né di
escludere:

```
review_status    = rejected_as_active_unit_due_to_insufficient_source_resolution
replacement_unit = PU-PMID-23344087-preclinical-unresolved-panel
rejected_for_lack_of_source_resolution = true
rejected_as_false                      = false
is_active                              = false
```

Il full text potrebbe riattivarle. Un record che le dicesse sbagliate lo
impedirebbe.

---

## 6. Le due unità attive

| Unità | Tipo | Ruolo |
|---|---|---|
| `PU-PMID-23344087-clinical-cohort` | `clinical_observational_cohort` | `clinical_observation` |
| `PU-PMID-23344087-preclinical-unresolved-panel` | `preclinical_in_vitro` | `unresolved_in_vitro_resistance_panel` |

### La coorte clinica

Sette pazienti ALK+ con resistenza acquisita al crizotinib dopo una mediana di 6
mesi (range 4-12). Tre con mutazioni secondarie di ALK, uno dei quali con
entrambe. Uno con copy number gain.

Il riarrangiamento di ALK **precede** il trattamento ed è criterio di ingresso
(`biomarker_role = enrolment_criterion`); le mutazioni di resistenza sono reperti
successivi e vivono in `acquired_findings`. Nessuna di esse entra nei requisiti
di arruolamento.

Crizotinib resta in `intervention` — è letterale nell'abstract — con
`intervention_role = prior_or_reference_therapy_not_study_intervention`: è la
terapia rispetto alla quale la resistenza è emersa, non un braccio assegnato.
`prior_therapies` resta **vuoto**: l'abstract non distingue formalmente terapia
precedente, trattamento dello studio e contesto di resistenza, e registrarlo come
terapia precedente sceglierebbe una delle tre letture. La decisione è tracciata in
`prior_therapy_decision`.

Restano `unknown`: `comparator`, `inclusion_criteria`, `exclusion_criteria`,
`prior_therapies`, `regimen`, `resection_status`, `stage`, `setting`,
`therapy_line`. Per gli ultimi tre la proposta source-checked aveva già annotato
il motivo — non sono ignoti per caso, l'abstract non li riporta affatto — e il
record lo conserva in `dimensions_not_reported_by_abstract`.

### Il tipo del pannello

`preclinical_in_vitro` è il tipo generico già presente in `UNIT_TYPES`.
`preclinical_engineered_model` o `preclinical_patient_derived_model` direbbero
**di che cosa** è fatto il pannello, che è esattamente la cosa che l'abstract non
dice: il tipo affermerebbe più della fonte. `UNIT_TYPES` non viene esteso.

---

## 7. La struttura non risolta del pannello

```
model_components                    = [SNU-2535, H3122 CR1, mutant clones]
model_component_count_known         = false
preclinical_model_composition       = not_separable
cellular_background_of_mutant_clones = unknown
component_to_statement_mapping      = not_separable
distinct_preclinical_system_count   = unknown
```

**`not_separable` e non `unknown`**, e nello stesso record convivono entrambi con
significati diversi:

- la **composizione** è `not_separable`: i componenti sono confermati, la loro
  relazione non è ricostruibile dal documento disponibile. Non è un buco da
  riempire cercando meglio;
- il **fondo cellulare dei cloni** è `unknown`: l'abstract non lo nomina affatto,
  quindi non c'è una relazione confermata da non separare.

Scriverli uguali perderebbe la differenza fra «smetti di cercare» e «cerca
meglio».

Le quattro affermazioni che l'abstract non sostiene sono **elencate** in
`not_asserted` invece di essere semplicemente omesse, così che un test possa
cercarle:

```
tutti i cloni derivano da SNU-2535           → not_asserted_by_source
tutti i cloni derivano da H3122 CR1          → not_asserted_by_source
SNU-2535 e i cloni sono la stessa unità      → not_asserted_by_source
il numero dei sistemi preclinici è noto      → false
```

Il pannello conserva anche le **due intensità** che l'abstract distingue nella
stessa frase, senza fonderle:

| Componente | Osservazione | Intensità |
|---|---|---|
| SNU-2535 | *«resistant to crizotinib treatment similar to H3122 CR1 cells»* | `resistant` |
| cloni L1196M e G1269A | *«less sensitive to crizotinib»* | `relative_reduced_sensitivity` |

Il pannello **non eredita i pazienti**: `population`, `stage`, `setting`,
`therapy_line`, `prior_therapies`, `resection_status`, `inclusion_criteria`,
`exclusion_criteria` sono tutte `not_applicable`.

E resta bloccato **oltre** una eventuale seconda revisione:

```
propagation_blocked_beyond_second_review = true
blocked_by                               = source_basis=abstract_only
unblock_conditions:
  - la composizione interna viene risolta su full text
  - una decisione finale autorizza esplicitamente una propagazione solo source-level
```

Una seconda lettura dello stesso abstract non risolverebbe niente: il limite non
è di chi legge.

---

## 8. `ES-V2-evidence-765` — `candidate_partial`

```
support_type  = clinical_observation_with_preclinical_validation
profile_units = clinical-cohort, preclinical-unresolved-panel
```

La fonte sostiene tutto ciò che serve perché il collegamento esista:

- `clinical_support` — due pazienti con G1269A fra i sette con resistenza
  acquisita (`B-clin-mutations`);
- `preclinical_support` — SNU-2535, derivata da un paziente con la mutazione
  G1269, resistente in modo simile a H3122 CR1; cloni G1269A meno sensibili
  (`B-pre-snu2535`, `B-pre-clones`).

I due supporti restano in campi **separati**, e
`preclinical_validation_is_clinical_response = false`: la riduzione di
sensibilità in coltura non è un esito clinico.

Ciò che la fonte non sostiene è una formulazione non qualificata di resistenza
completa — vedi sezione seguente — e la composizione del pannello, che resta
`not_separable` anche a livello di statement:
`component_to_statement_mapping = not_separable`.

---

## 9. «less sensitive» non è «resistance»

```
source_term              = less sensitive to crizotinib
statement_term           = resistance
mapping_type             = evidence_strength_normalization
mapping_status           = requires_terminology_verification
resistance_qualifier     = relative_reduced_sensitivity
complete_resistance      = false
claim_strength_alignment = partial
assertion_conflict       = false
uncertain_dimension      = claim_strength
```

L'abstract distingue due intensità **nella stessa frase**: SNU-2535 è
«resistant», i cloni mutanti sono «less sensitive». Lo statement dice
«resistance» senza qualificatore.

La differenza non è un conflitto — la fonte non nega la resistenza — e
classificarla come tale renderebbe lo statement scartabile invece che
qualificabile. Ma non è nemmeno un sinonimo: trasformare una riduzione relativa
in resistenza completa aggiungerebbe forza che la fonte non fornisce.

Il mapping resta `requires_terminology_verification` e non viene promosso a
`verified_synonym`.

---

## 10. `ES-V2-evidence-767` — `candidate_ambiguous`

```
support_type         = direct_clinical_support_with_confounded_causal_attribution
evidence_granularity = case_level
population_scope     = single_patient
subset_size / cohort_size = 1 / 7
cohort_generalizable = false
frequency_inference  = forbidden
case_identifier      = unknown
```

Un solo paziente dei sette ha mostrato copy number gain di ALK, con un aumento di
4.1 volte rispetto al campione pre-crizotinib.

**Il case identifier resta `unknown`.** L'abstract dice *«one patient displayed
ALK gene copy number gain»* e non lo numera; nessuno dei sei locator verificati
porta un identificatore. Inventarne uno sarebbe l'unico modo di far sembrare
tracciabile un caso che non lo è. Un test rilegge il locator `B-clin-cng` dagli
artefatti source-checked e verifica che non contenga alcun `#`: senza quel
controllo, `unknown` sarebbe una asserzione senza prova.

La granularità è protetta dalla policy della fase precedente, non da una regola
nuova: `case_level_to_cohort_population`, `case_level_frequency_inference`,
`case_level_to_enrolment_requirement` sono le stesse introdotte per PMID
22235099, e `policy_reused_from` lo dichiara nel record. Le regole vengono
**eseguite** sulle decisioni prima che vengano scritte, non assunte.

---

## 11. La co-occorrenza di EGFR L858R

```
cooccurring_alterations    = [EGFR L858R]
cooccurrence_detail        = EGFR L858R mutation with high polysomy
causal_attribution         = not_separable
isolated_mechanism_support = false
confounding_status         = molecular_cooccurrence
assertion_conflict         = false
source_contradicts_statement = false
```

Lo stesso unico paziente portava anche EGFR L858R con polisomia elevata.
Attribuire la resistenza al copy number gain di ALK sceglie una delle due
spiegazioni senza che la fonte lo faccia.

**Perché `ambiguous` e non `conflicting`.** La distinzione non è di sfumatura:
`conflicting` direbbe che la fonte contraddice lo statement, e la fonte non lo
contraddice. Dice meno, e in un modo preciso. Il campo `why_not_conflicting`
scrive la ragione nel record invece di lasciarla dedurre.

Le annotazioni di confondimento vivono in un file proprio, separate da quelle
case-level. Un caso singolo ha un denominatore troppo piccolo; un caso confuso ha
un denominatore qualunque e due spiegazioni. Sommarli sotto la stessa etichetta
perderebbe il motivo per cui lo statement non è utilizzabile.

---

## 12. `ALK gene copy number gain` → `ALK Amplification`

```
mapping_type    = biomarker_strength_normalization
mapping_status  = requires_terminology_verification
literal_equivalence                   = false
source_supports_broader_concept       = true
source_supports_exact_normalized_term = not_verified
kg_used_as_sole_authority             = false
source_native_term                    = ALK gene copy number gain
amplification_used_as_source_native   = false
```

L'abstract riporta il reperto come «copy number gain», quantificato. La stringa
«amplifications» compare una volta, nei **metodi**, per dire che cosa è stato
*analizzato* (*«analyzed for ALK, EGFR, and KRAS mutations and ALK and EGFR gene
amplifications»*) — non per descrivere il reperto. Il valore source-native resta
quello del risultato.

È lo stesso scarto già registrato su PMID 22235099, e resta non verificato per la
stessa ragione: «amplification» ha in oncologia una soglia propria, e il grafo
congelato non può essere l'unica autorità della propria normalizzazione.

---

## 13. Propagation policy

Entrambe le unità nascono così:

```
review_status                      = first_review_complete
cohort_state                       = reviewed_pending_independent_review
human_reviewed                     = true
clinical_reviewer                  = false
independent_review                 = false
propagation_eligibility            = prototype_only
may_display_qualifiers             = true
is_propagatable                    = false
is_hard_filterable                 = false
is_evaluable                       = false
requires_second_independent_review = true
source_basis                       = abstract_only
```

Nessuno di questi valori è dichiarato a mano: `prototype_only` viene dalla
politica, che lo assegna a qualunque prima revisione non indipendente, e lo
script verifica il risultato invece di scriverlo.

La risoluzione della coorte **non** è usata come autorizzazione. Sono due domande
diverse: a chi si applica il valore, e chi lo ha confermato.

Il pannello preclinico porta in più `propagation_blocked_beyond_second_review`:
resterà non propagabile anche dopo una seconda revisione, finché la composizione
interna non viene risolta o una decisione finale autorizza esplicitamente una
propagazione solo a livello di fonte.

---

## 14. Provenienza

`qualifier_provenance_completeness = 1.000`. Ogni dimensione nota di ogni unità
porta una voce di provenienza, e il costruttore solleva se una manca.

Ogni voce porta la catena completa — identificatore della fonte, hash
dell'abstract, locator, metodo di estrazione, revisore, ruolo, metodo di
revisione, data — **più `source_basis`**. Le due dimensioni che l'autore ha
fissato leggendo entrambe le proposte precliniche (`evidence_design`,
`comparator`) portano `value_origin = author_approved_unresolved_panel` invece di
`source_document`: risolvono una divergenza fra due letture, e far sembrare che
una frase dell'abstract le contenga già sarebbe il modo più rapido di perdere la
distinzione.

Dove le proposte divergono su una decisione di campo e l'autore non ha fissato un
valore, la decisione diventa `not_separable`: due letture diverse dello stesso
abstract sono la prova che la dimensione non è risolvibile, non un motivo per
sceglierne una.

---

## 15. Perché serve una seconda revisione

Le tre distinzioni che il corpus tiene separate valgono qui come nelle due fasi
precedenti:

- `human_reviewed` ≠ `clinical_reviewed`;
- `first_review_complete` ≠ `independent_review`;
- una revisione completata ≠ gold valutabile.

Il gold resta `provisional_first_review`; le decisioni vivono in
`first_review_annotation`, non in `final_status`; `second_annotator`, `agreement`
e `adjudication` restano `null`. Le tre annotazioni della fase precedente su PMID
22235099 sopravvivono nel file: una fase nuova aggiunge, non riscrive.

I 70 packet ciechi sono byte-identical prima e dopo, e questa volta il controllo
copre anche **tre fasi già approvate** — `author_approval` (11 file),
`author_approval_22235099` (16 file), `first_review` (13 file) — tutte invariate.

Nessuna metrica finale è calcolata.

---

## 16. Perché potrebbe servire il full text

A differenza delle due fonti precedenti, qui una seconda revisione indipendente
**non basta** a chiudere tutte le domande aperte. Due lettori dello stesso
abstract non possono scoprire il fondo cellulare dei cloni, perché l'abstract non
lo contiene.

Le domande che restano aperte e ciò che le chiuderebbe:

| Domanda | Serve |
|---|---|
| su quale fondo sono costruiti i cloni? | full text |
| quanti sistemi preclinici distinti esistono? | full text |
| SNU-2535 e i cloni sono la stessa unità sperimentale? | full text |
| quale paziente aveva il copy number gain? | full text |
| «less sensitive» corrisponde a resistenza clinica? | verifica terminologica |
| il CNG di ALK o EGFR L858R spiegano la resistenza? | non risolvibile da questa fonte |

Il record `unresolved_structure_records.jsonl` esiste perché queste domande siano
interrogabili invece che sepolte nella prosa: la prossima fase che volesse sapere
quali unità aspettano un full text non deve rileggere i report.

---

## 17. Chiusura del batch clinico/preclinico

```
clinical_preclinical_author_approval_batch_complete = true
author_approvals_completed = 3
author_approvals_pending   = 0
```

Tre fonti, tre approvazioni, tre esiti diversi — ed è il punto:

| Fonte | Verdetto dell'audit | Esito della revisione |
|---|---|---|
| PMID 31358542 | `split_required` | **respinto**: nessun esperimento proprio, solo una citazione |
| PMID 22235099 | `split_required` (2 unità) | **confermato con più unità**: 4 attive |
| PMID 23344087 | `split_required` (2 unità) | **parzialmente sostenuto**: 2 attive, composizione non risolta |

Il rilevatore ha ragione sulla presenza in due casi su tre, e non ha mai ragione
sul conteggio. Il caso di questa fonte è registrato come positivo **parziale**:

```
reference_case_type                     = partially_confirmed_clinical_preclinical_mixture
detector_presence_signal_correct        = true
detector_granularity_prediction_correct = false
ground_truth_available                  = false
use_as_regression_case                  = true
use_for_detector_performance_estimation = false
detector_promoted                       = false
```

`ground_truth_available = false` è la differenza rispetto ai due casi precedenti,
e il terzo principio della serie:

```
an_unreadable_structure_is_not_a_detector_error
```

Là il rilevatore aveva torto sulla presenza (31358542) o sul conteggio
(22235099). Qui non è il rilevatore ad avere torto: è il documento a non bastare.
Non esiste un numero corretto di unità contro cui misurare la previsione, quindi
il caso resta di regressione e non entra in nessuna stima.

Il rilevatore non viene promosso. Tre casi non misurano niente.

**Prossimo passo:** rigenerazione versionata del qualification corpus,
aggiornamento degli hash e nuovo snapshot fingerprint. La coda standard non
riprende in questo branch.
