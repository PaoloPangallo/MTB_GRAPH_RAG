# Approvazione della prima revisione — PMID 22235099

**Decisione: `approve_with_corrections`.** Approvata da Paolo Pangallo, autore
della tesi, con assistenza LLM nella preparazione documentale.

---

## 1. Fonte

| | |
|---|---|
| PMID | `22235099` |
| PMC | `PMC3311875` |
| Oggetto | meccanismi molecolari di resistenza al crizotinib in NSCLC ALK+ |
| Parent unit | `PU-PMID-22235099-cohort-1` |
| Disponibilità | `full_text` |
| Hash del documento | `ff9615e75fe8e274c9cc9656bfee3b4b55d867306102f995bd45c6c6086b3e32` |
| Locator | **12/12 verificati**, `{"exact": 12}` |
| Statement | `ES-V2-evidence-4288`, `ES-V2-evidence-764`, `ES-V2-evidence-766` |

Hash e locator sono stati confrontati con `source_access_verification.jsonl`
**prima** che qualunque record venisse scritto. Approvare un report e scoprire
dopo che l'artefatto descrive un altro documento produrrebbe una decisione umana
attaccata alla fonte sbagliata, che è peggio di nessuna decisione.

---

## 2. Decisione strutturale

```
author_decision                = approve_with_corrections
structural_decision            = audit_split_confirmed_with_more_units
clinical_preclinical_split     = confirmed
audit_proposed_units           = 2
source_review_proposed_units   = 5
author_approved_units          = 4
parent_state                   = superseded_by_reviewed_restructure
```

Lo split è **confermato**: a differenza di PMID 31358542, questa pubblicazione
contiene esperimenti propri e non citati. Metodi, figure e risultati preclinici
esistono, e sono ancorati a locator verificati.

Ciò che la revisione dell'autore corregge è il **numero** delle parti, non la
loro esistenza.

---

## 3. Perché due unità non bastavano

La proposta dell'audit separava «clinico» da «preclinico», due categorie. Ma la
componente preclinica non è un sistema: sono quattro, e le differenze non sono
descrittive.

| Sistema | Fondo | Saggio | Direzione |
|---|---|---|---|
| Ba/F3 + costrutti EML4-ALK | linea murina IL-3 dipendente | proliferazione, IC50 | resistenza relativa |
| NIH3T3 + stessi costrutti | fibroblasti murini | colonie in soft agar, immunoblot | resistenza relativa |
| CUTO-1 vs H3122 / H2228 | linea derivata dal paziente #10 | proliferazione comparativa | resistenza marcata |
| H3122 + KRAS G12V | linea NSCLC EML4-ALK+ | proliferazione, IC50 | **nessuna differenza** |

Con una sola unità preclinica, il quarto esperimento — che argomenta *contro* una
ipotesi — sarebbe stato mescolato ai tre che ne sostengono altre. Il risultato
sarebbe stato un blocco preclinico che «mostra resistenza», e la riga che dice il
contrario sarebbe diventata invisibile.

Anche il terzo caso avrebbe sofferto: CUTO-1 ha perso il bersaglio che i modelli
ingegnerizzati portano per costruzione, e fonderla con loro avrebbe fatto
sembrare controllato un esperimento che non lo è.

---

## 4. Perché cinque unità erano troppe

Ba/F3 e NIH3T3 differiscono per fondo cellulare e per saggio, e la revisione
documentale aveva usato proprio questo per tenerle separate: «la conferma vale
perché sono due sistemi, e fonderli la farebbe contare una volta sola».

L'osservazione è giusta e la conclusione no. Due sistemi rendono la conferma più
**solida**, non doppia. Ciò che i due esperimenti condividono è tutto quanto
definisce una unità epistemica:

```
stessa alterazione principale   ALK G1269A su fondo di fusione EML4-ALK
stesso farmaco                  crizotinib
stessa proposizione biologica   G1269A conferisce resistenza al crizotinib
stessa direzione del risultato  resistenza relativa, non completa
stessi statement candidati      ES-V2-evidence-764
```

Due unità distinte avrebbero fatto contare due volte una conferma sola: uno
statement collegato a entrambe avrebbe avuto due supporti preclinici invece di
uno verificato due volte. La differenza si vedrebbe in qualunque conteggio di
copertura.

---

## 5. Le quattro unità approvate

| Unità | Tipo | Ruolo | Polarità |
|---|---|---|---|
| `PU-PMID-22235099-clinical-cohort` | `clinical_observational_cohort` | `clinical_observation` | `supports` |
| `PU-PMID-22235099-engineered-isogenic-models` | `preclinical_engineered_model` | `functional_validation` | `supports` |
| `PU-PMID-22235099-cuto1-comparative` | `preclinical_patient_derived_model` | `comparative_pharmacology` | `supports` |
| `PU-PMID-22235099-h3122-kras-engineered` | `preclinical_engineered_model` | `negative_experiment` | `does_not_support` |

I `unit_type` vengono dal vocabolario esistente. Il brief ne nominava tre che non
esistono — `preclinical_engineered_model_functional_validation`,
`patient_derived_preclinical_model`,
`preclinical_engineered_model_negative_experiment` — ma non sono tipi: `UNIT_TYPES`
dice **che cosa** è l'unità, mentre «validazione funzionale» e «esperimento
negativo» dicono a che cosa serve. Coniare un tipo per ogni combinazione avrebbe
reso `is_preclinical` dipendente dall'esito dell'esperimento. Il ruolo vive in
`experiment_role` e `assertion_polarity`.

### La coorte clinica

Il riarrangiamento di ALK è **criterio di arruolamento** (`biomarker_role =
enrolment_criterion`, locator `A-clin-cohort`). Le sei alterazioni di resistenza
sono **reperti successivi** e vivono in `acquired_resistance_findings`. Tenerli
nello stesso campo li renderebbe indistinguibili, e un reperto letto come
requisito farebbe sembrare selezionata una popolazione che non lo era.

Crizotinib resta in `intervention` — è verificato — ma con
`intervention_role = prior_or_reference_therapy_not_study_intervention`: è la
terapia rispetto alla quale la resistenza è emersa, non il braccio di un trial.
`prior_therapies` resta vuoto: rappresentarlo come terapia precedente richiede di
fissare rispetto a *cosa* è precedente, e la fonte non lo dice in una forma che il
modello attuale registri senza inferenza. Il farmaco non si perde — è già nel
record — e la decisione è tracciata in `prior_therapy_decision`.

Restano `unknown`: `comparator`, `inclusion_criteria`, `exclusion_criteria`,
`regimen`, `resection_status`, `setting`, `stage`, `therapy_line`.

**Correzione al brief.** La popolazione non è «14 pazienti con resistenza
acquisita». La fonte ne conta **12 acquisite e 2 intrinseche**, e l'abstract lo
dice esplicitamente («mechanisms of intrinsic and acquired resistance»). La
formulazione aggregata avrebbe reso acquisita una resistenza che non lo era. Il
record conserva la formulazione verificata più
`resistance_subgroups = {acquired: 12, intrinsic: 2}`.

---

## 6. La consolidazione Ba/F3 + NIH3T3

Le due proposte non sono cancellate. Restano in `parent_unit_history.jsonl` con:

```
review_status     = replaced_by_author_approved_consolidation
replacement_unit  = PU-PMID-22235099-engineered-isogenic-models
is_active         = false
is_propagatable   = false
```

Cancellarle renderebbe invisibile che la revisione documentale aveva proposto
cinque unità, e la differenza fra cinque e quattro *è* la decisione.

L'unità consolidata conserva le due letture separate in `model_instances`:
ciascuna con il proprio saggio, il proprio endpoint, i propri locator e la
proposta da cui viene. La consolidazione riassume, non annulla.

Un solo valore non viene da una singola proposta: `evidence_design` descrive due
saggi. La sua provenienza lo dichiara — `value_origin =
author_approved_consolidation`, asserito dal revisore — invece di far sembrare
che una frase della fonte lo contenga già.

---

## 7. L'autonomia di CUTO-1

CUTO-1 deriva dal paziente #10 e **non è** il paziente #10. La relazione è
registrata come derivazione, non come identità:

```
derived_from_clinical_case            = patient_10
derivation_relation                   = clinical_case -> derived_model
derivation_is_identity                = false
cross_context_biomarker_propagation   = forbidden
```

Il modello ha perso il riarrangiamento di ALK che il paziente aveva. È
esattamente la ragione per cui l'unità esiste separata: se il biomarcatore
clinico attraversasse il confine, il modello sembrerebbe portare un bersaglio che
non ha, e la sua resistenza al crizotinib diventerebbe la prova di una cosa
diversa da quella che è.

`biomarker_requirements` resta vuoto. `inherited_from_clinical_case` è una lista
vuota, e `not_inherited_from_clinical_case` elenca esplicitamente biomarcatore,
popolazione, setting, linea terapeutica, stadio e altre alterazioni.

**Limite dichiarato.** La perdita del riarrangiamento è asserita dalla revisione
source-checked e nessuno dei 12 locator verificati la ancora a una frase propria.
Il record lo dice:
`ALK_loss_locator_status = asserted_by_source_checked_review_without_dedicated_locator`
e `ALK_loss_requires_locator_verification = true`. Registrarla senza dirlo la
farebbe sembrare verificata quanto il resto.

La ri-tipizzazione da `preclinical_in_vitro_comparative_pharmacology` a
`preclinical_patient_derived_model` è una correzione: l'origine da paziente è la
proprietà che governa i divieti di propagazione, non un dettaglio descrittivo. Il
disegno comparativo resta in `evidence_design` e i comparatori H3122/H2228
restano dove erano.

---

## 8. L'esperimento negativo H3122/KRAS

```
hypothesis_tested       = KRAS G12V confers crizotinib resistance
result_direction        = no_significant_difference
assertion_polarity      = does_not_support
must_not_be_read_as     = KRAS G12V -> resistance to crizotinib
cohort_generalizable    = false
```

Il locator `A-pre-kras-negative` è verbatim: «The IC₅₀ of H3122 expressing KRAS
G12V was not significantly different from H3122 harboring the empty vector».

Il risultato non è rimosso dal corpus, e ha un record proprio
(`negative_experiment_records.jsonl`) perché è il più facile da perdere: non
produce statement, non entra in nessun link, e sparirebbe senza che una metrica se
ne accorgesse. Resta visibile nel prototipo con
`propagation_eligibility = prototype_only` e `is_propagatable = false`.

`assertion_polarity` non è una nota: è il campo che impedisce la lettura sbagliata
anche a chi la nota non la legge.

---

## 9. Le decisioni sui tre statement

Nessuna cambia lo stato del candidato. La revisione documentale aveva letto bene;
ciò che l'approvazione aggiunge è il **denominatore**.

### `ES-V2-evidence-764` — `candidate_valid`

```
support_type   = clinical_observation_with_preclinical_validation
profile_units  = clinical-cohort, engineered-isogenic-models
```

È l'unico statement della fonte in cui osservazione clinica e validazione
preclinica coesistono, e per questo l'unico in cui possono confondersi. I due
supporti restano in campi separati:

- `clinical_support` — G1269A osservata in due pazienti (#6, #7) alla progressione
  su crizotinib (`A-clin-g1269a`);
- `preclinical_support` — validazione funzionale su Ba/F3 e NIH3T3
  (`A-pre-baf3-result`, `A-pre-nih3t3`).

`preclinical_validation_is_clinical_response = false`. La validazione mostra
resistenza in coltura, non risposta clinica. E la resistenza mostrata è
**relativa**, intermedia fra C1156Y e L1196M: `resistance_qualifier =
relative_resistance` conserva ciò che lo statement non dice.

### `ES-V2-evidence-4288` — `candidate_partial`, `case_level`

```
evidence_granularity     = case_level
population_scope         = single_patient
case_identifier          = patient_9   (verificato, A-clin-egfr)
subset_size / cohort_size = 1 / 14
cohort_generalizable     = false
```

EGFR L858R alla progressione è documentata in un solo paziente, e la lesione
ri-biopsiata aveva perso il riarrangiamento di ALK. Trattarla come proprietà della
coorte estenderebbe a quattordici pazienti ciò che si è visto in uno.

### `ES-V2-evidence-766` — `candidate_partial`, `named_patient_subset`

**Discrepanza col brief, registrata e non risolta in silenzio.**

Il brief prevedeva `case_identifier = patient_8`. Il locator `A-clin-cng`, che il
batch ha verificato come `exact`, dice altro:

> «Two patients demonstrated a marked increase in abnormal signal copy number
> (#7 at 5-fold and #8 at >4 fold), consistent with CNG of the ALK gene fusion»

Lo statement porta il biomarcatore `EML4::ALK Fusion AND ALK Amplification`:
copre il reperto CNG su **due** pazienti nominati, non il caso del solo #8. Il CNG
*isolato* — senza mutazione concomitante del dominio chinasico — poggia sul solo
#8, perché #7 portava anche G1269A.

Registrazione approvata:

```
evidence_granularity          = named_patient_subset
population_scope              = named_patients_subset
subset_size / cohort_size     = 2 / 14
case_identifiers              = [patient_7, patient_8]
narrowest_case_identifier     = patient_8
isolated_cng_case_identifier  = patient_8
cohort_generalizable          = false
frequency_inference           = forbidden
```

Nessun identificatore è inventato: entrambi compaiono letteralmente nel locator
verificato. E nessuno è stato scartato per far tornare il conto: `case_level`
avrebbe detto «uno» quando sono due.

In questa fonte non esiste alcun esperimento sul copy number gain. Il supporto
preclinico che la letteratura riporta viene da un'altra pubblicazione, qui citata:
`preclinical_support_in_this_source = false`.

---

## 10. La granularità come regola generale

Il livello `named_patient_subset` non esiste per questa fonte. Esiste perché
`case_level` significa «un paziente» e `subgroup_level` implica un denominatore,
e due pazienti nominati non sono né l'uno né l'altro.

Da un livello non generalizzabile discendono tre divieti, derivati e non scritti a
mano su ogni record (`constraints_for`):

```
evidence_granularity ∈ {case_level, named_patient_subset}
→ cohort_generalizable          = false
→ population_level_propagation  = forbidden
→ frequency_inference           = forbidden
→ enrolment_requirement_promotion = forbidden
```

Tre regole eseguibili con errore tipizzato li fanno rispettare
(`propagation_guards/1.2`):

| Regola | Errore | Impedisce |
|---|---|---|
| `case_level_to_cohort_population` | `CaseLevelPropagationError` | singolo paziente → coorte, → popolazione |
| `case_level_frequency_inference` | `CaseLevelFrequencyError` | osservazione isolata → frequenza |
| `case_level_to_enrolment_requirement` | `CaseLevelEnrolmentError` | reperto acquisito → requisito di arruolamento |

Nessuna nomina questa fonte, e un test lo verifica: legare la regola a un PMID la
renderebbe inapplicabile al successivo. Le regole girano sulle decisioni **prima**
che vengano scritte — una decisione può dichiararsi case-level e generalizzabile
insieme e restare sintatticamente valida, ed è così che un caso singolo diventa
una coorte senza che nessuno lo abbia deciso.

`unknown` non è fra i livelli che bloccano: non sapere il denominatore non è
sapere che è piccolo, ed è un problema diverso.

---

## 11. Il mapping copy number gain / amplification

```
source_term      = copy number gain of the ALK gene fusion
statement_term   = ALK Amplification
mapping_type     = biomarker_strength_normalization
mapping_status   = requires_terminology_verification
literal_equivalence                    = false
source_supports_broader_concept        = true
source_supports_exact_normalized_term  = not_verified
uncertain_dimension                    = biomarker_specificity
```

La fonte definisce il CNG come «più del doppio» delle copie medie. In oncologia
«amplification» ha una soglia diversa e più alta, e la stringa non compare nel
documento. Non sono sinonimi verificati.

Il mapping **non** viene promosso a `verified_synonym`, e
`kg_used_as_sole_authority = false`: la normalizzazione viene dallo statement del
grafo congelato, e usare il grafo come prova della propria normalizzazione è
circolare.

---

## 12. Propagation policy

Tutte e quattro le unità nascono così:

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
```

Nessuno di questi valori è dichiarato a mano. `prototype_only` viene dalla
politica esistente, che lo assegna a qualunque prima revisione non indipendente,
e lo script verifica il risultato invece di scriverlo. Il blocco alla propagazione
non dipende da una riga che qualcuno potrebbe dimenticare: lo stato
`reviewed_pending_independent_review` semplicemente non compare fra quelli
propagabili.

`resolved_cohort` **non** è usato come autorizzazione. La struttura della coorte
risponde alla domanda «a chi si applica il valore»; l'eligibility risponde a «chi
lo ha confermato». Sono domande diverse, e per un periodo il repository le teneva
sotto la stessa bandiera.

Mostrare un qualificatore sbagliato lo espone a chi può correggerlo. Filtrare con
un qualificatore sbagliato rimuove evidenza che nessuno vedrà più. È per questo
che `may_display_qualifiers` è vero e `is_hard_filterable` è falso.

---

## 13. Provenienza

`qualifier_provenance_completeness = 1.000`. Ogni dimensione nota di ogni unità
porta una voce di provenienza, e il costruttore solleva se una manca.

Ogni voce porta la catena completa: identificatore della fonte, hash del
documento, locator, metodo di estrazione, revisore, ruolo del revisore, metodo di
revisione, data. La provenienza documentale dice *da dove* viene il valore; senza
revisore e metodo non direbbe *chi risponde* di quel valore.

Le voci ereditate dalle due proposte consolidate restano distinte anche quando
riguardano la stessa dimensione, e ciascuna porta `derived_from_proposal_id`:
ciascun modello ha letto la fonte per conto proprio, e fonderle farebbe sparire il
fatto che le letture erano due.

---

## 14. Perché serve una seconda revisione

Questa revisione è di una persona sola, che non è un clinico, su materiale
preparato con assistenza LLM. Tre cose che il corpus tiene separate e che questa
fase non collassa:

- `human_reviewed` ≠ `clinical_reviewed`. L'autore non è un clinico, e una prima
  revisione non clinica non vale come validazione clinica.
- `first_review_complete` ≠ `independent_review`. Chi ha approvato ha letto
  materiale preparato da una macchina: la seconda revisione serve proprio perché
  la prima non è indipendente.
- una revisione completata ≠ gold valutabile. `is_evaluable` resta falso finché
  esiste una sola annotazione.

Il gold resta `provisional_first_review`. Le decisioni vivono in
`first_review_annotation`, non in `final_status`: copiarle darebbe al linker una
precision misurata contro un solo giudizio, non indipendente e non clinico.
`second_annotator`, `agreement` e `adjudication` restano `null`.

I 70 packet ciechi della seconda revisione sono byte-identical prima e dopo, e i
test cercano al loro interno le stringhe che *questa fase ha deciso* — non i
termini che compaiono nei packet come vocabolario ammesso.

Nessuna metrica finale è calcolata: precision, recall, F1, agreement, accuratezza
del rilevatore, applicabilità clinica, qualità del retrieval restano
`not_calculated`.

---

## 15. Limiti

- la revisione è documentale e non clinica: l'autore non è un clinico;
- la preparazione del materiale è assistita da LLM, quindi la prima revisione non
  è indipendente;
- il numero esatto di pazienti per ciascun meccanismo si legge nelle tabelle, non
  nel testo corrente: i conteggi qui registrati vengono dalle frasi ancorate a
  locator;
- la perdita del riarrangiamento di ALK in CUTO-1 è asserita dalla revisione
  source-checked e non ancorata a un locator proprio;
- il mapping copy number gain / amplification resta non verificato: nessuna soglia
  condivisa è stata confrontata;
- due casi confermati non permettono di stimare precision, recall o accuratezza
  del rilevatore;
- le osservazioni su singoli pazienti restano dentro l'unità della coorte: la
  granularità le distingue, ma non esiste una unità separata per ciascuna.

**Rischio residuo.** La coorte clinica contiene osservazioni a livello di singolo
paziente (#9 per EGFR, #8 per il CNG isolato) che non sono proprietà della coorte.
La granularità dichiarata le protegge; una lettura che la ignorasse le
propagherebbe.

---

## Il caso del rilevatore

```
reference_case_type                     = confirmed_clinical_preclinical_mixture
detector_original_verdict               = split_required
reviewed_verdict                        = split_required_with_more_units
detector_presence_signal_correct        = true
detector_granularity_prediction_correct = false
use_as_regression_case                  = true
use_for_detector_performance_estimation = false
detector_promoted                       = false
```

Il rilevatore ha visto entrambe le componenti, e le ha viste bene: 9 occorrenze di
«Ba/F3», 26 di «cell lines», 11 di «in vitro», 133 di «patients». Non ha visto che
i sistemi preclinici erano quattro, perché nessun segnale conta i modelli
distinti. Il verdetto era giusto, il numero no.

```
detecting_a_mixture != counting_its_parts
```

È il principio speculare a quello stabilito da PMID 31358542
(`term_present_in_document != evidence_generated_by_current_study`). Là, un
segnale presente senza evidenza propria; qui, evidenza propria presente ma contata
male. Vedere una struttura e contarne le parti sono capacità diverse, e nessuna
soglia converte la prima nella seconda.

Il rilevatore non viene promosso. Due casi confermati non misurano niente.

---

## Prossimo passo

`SOURCE_REVIEW_PMID-23344087.md`. La coda standard non riprende in questo branch.
