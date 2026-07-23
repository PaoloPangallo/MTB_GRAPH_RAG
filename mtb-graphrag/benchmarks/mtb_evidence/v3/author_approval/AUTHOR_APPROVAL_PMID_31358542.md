# Approvazione della prima revisione — PMID 31358542

**Decisione: `approve_with_corrections`.** Approvata da Paolo Pangallo, autore
della tesi, con assistenza LLM nella preparazione documentale.

---

## 1. Fonte

| | |
|---|---|
| PMID | `31358542` |
| PMC | `PMC6858956` |
| Titolo | *Treatment with Next-Generation ALK Inhibitors Fuels Plasma ALK Mutation Diversity* |
| Parent unit | `PU-PMID-31358542-cohort-1` |
| Unità attiva | `PU-PMID-31358542-clinical-cohort` |
| Statement | `ES-V2-evidence-100003`, `ES-V2-evidence-100004` |

---

## 2. Decisione strutturale

```
author_decision              = approve_with_corrections
structural_decision          = audit_split_not_supported
clinical_preclinical_split   = rejected
final_number_of_profile_units = 1
```

La fonte è registrata come caso **interamente clinico**. Nessuna unità
preclinica esiste, e nessuna viene mantenuta attiva.

Una precisazione di vocabolario che non è cosmetica: il risultato **non è uno
split**. Lo split è ciò che è stato respinto. La parent passa quindi a
`superseded_by_reviewed_restructure` e non a `superseded_by_reviewed_split`,
perché il secondo descriverebbe il contrario di quanto deciso.

---

## 3. Perché era un falso positivo

L'audit strutturale aveva classificato la fonte `clinical_preclinical_split_required`
sulla base di **una sola** occorrenza lessicale di «in vitro», che è questa:

> «Based on in vitro models, a G1269A/I1171S compound mutation may re-sensitize to
> ceritinib or brigatinib.²³»

La frase sta nella Discussione e attribuisce il reperto a modelli di un lavoro
**citato** (riferimento 23). Nella pubblicazione non esistono metodi preclinici
propri, né figure né risultati preclinici: nessuna linea cellulare, nessun
xenograft, nessun IC50, nessuna trasfezione.

Il rilevatore non ha sbagliato a leggere. Ha sbagliato a inferire, e l'inferenza
sbagliata è generale:

```
term_present_in_document != evidence_generated_by_current_study
```

---

## 4. Unità clinica approvata

```
profile_unit_id                    = PU-PMID-31358542-clinical-cohort
unit_type                          = clinical_observational_cohort
cohort_state                       = reviewed_pending_independent_review
review_status                      = first_review_complete
human_reviewed                     = true
clinical_reviewed                  = false
independent_review                 = false
is_propagatable                    = false
is_evaluable                       = false
requires_second_independent_review = true
```

`human_reviewed = true` dice soltanto che l'autore ha approvato la prima
revisione. Non dice che un clinico l'abbia validata, e i due campi restano
separati proprio perché la distinzione si perde con facilità.

L'unità **non propaga**. Lo stato `reviewed_pending_independent_review` non
compare fra quelli propagabili, quindi il blocco non dipende da un controllo che
qualcuno potrebbe dimenticare di scrivere.

> **Nota su una divergenza dal precedente.** Le quattro unità revisionate di
> PMID 22277784 risultano `resolved_cohort` e quindi **propagabili** dopo una
> prima revisione anch'essa non indipendente. Qui si è scelto il contrario. È una
> incoerenza reale del corpus: o quelle quattro vanno riportate a uno stato non
> propagabile, o questa scelta è troppo stretta. La decisione non è di questa
> fase, ma va presa prima che il retrieval qualificato legga le unità.

---

## 5. Gli otto sottogruppi

La fonte descrive otto sottopopolazioni sovrapposte: 70 pazienti in progressione
su TKI di seconda generazione, 29 su lorlatinib, 46 con plasma alla progressione
su alectinib, 41 biopsie tissutali, 12 appaiati, 6 alectinib→brigatinib, 15 con
lorlatinib dopo un TKI di seconda generazione, 19 con recidiva solo cerebrale o
toracica.

**Nessuna diventa una unità.**

```
analyzed_subgroups_count                        = 8
subgroup_overlap                                = true
requires_subgroup_unit_split                    = false
subgroup_specific_results_globally_propagatable = false
intervention_attribution                        = not_separable
```

Sono analisi sovrapposte dello stesso denominatore. Crearne otto unità
moltiplicherebbe la stessa coorte per otto, e ciascuna sembrerebbe indipendente
dalle altre.

Una futura suddivisione sarà ammessa solo se ricorrono **tutte** e quattro le
condizioni: uno statement riguarda esplicitamente un singolo sottogruppo;
denominatore e intervento sono separabili; il risultato è subgroup-specific; la
propagazione globale produrrebbe un errore.

---

## 6. `ES-V2-evidence-100003` → `candidate_invalid`

Corretto da `candidate_ambiguous`.

| | |
|---|---|
| `invalid_reason` | `aggregate_to_specific_intervention_attribution` |
| `source_claim_scope` | `second_generation_alk_tki_class` |
| `statement_claim_scope` | `brigatinib` |
| `intervention_attribution` | `unsupported_by_this_source` |
| dimensione non sostenuta | `intervention` |

La fonte riporta la frequenza di G1202R per la **classe** dei TKI ALK di seconda
generazione — 23 su 70 specimen, 33% — mentre lo statement la attribuisce
specificamente a **brigatinib**.

Non è `not_determinable`, ed è una distinzione che vale la pena difendere: il
full text è disponibile e la mancata attribuzione specifica è **verificabile**.
`not_determinable` direbbe che non lo sappiamo; qui lo sappiamo.

Nota epistemica: lo statement potrebbe essere sostenuto da un'altra fonte.
Questa non sostiene la formulazione attribuita a brigatinib.

---

## 7. `ES-V2-evidence-100004` → resta `candidate_partial`

**Dimensioni sostenute:** `disease`, `ALK rearrangement`, `clinical resistance
context`.

**Dimensioni non sostenute o non separabili:** attribuzione al singolo
intervento, denominatore esatto del sottogruppo, frequenza drug-specific.

La fonte sostiene il contesto clinico generale ma non permette di attribuire con
sicurezza il risultato aggregato a un farmaco o a un sottogruppo. Un risultato di
classe non si propaga a un farmaco singolo.

---

## 8. Provenienza

**Provenance completeness: 1.000.**

Ogni campo noto porta ora la catena completa: identificatore della fonte,
locator, span hash, hash del documento, metodo di estrazione, revisore, ruolo del
revisore, metodo di revisione, data. Da dove viene il valore era già tracciato;
chi ne risponde no.

I campi non sostenuti dalla fonte restano `unknown` — `comparator`,
`exclusion_criteria`, `inclusion_criteria`, `prior_therapies`, `regimen`,
`resection_status`, `setting`, `stage` — e `intervention` resta `not_separable`.
Nessuno è stato inventato.

---

## 9. Caso di riferimento del rilevatore

```
detector_reference_case                   = true
reference_case_type                       = citation_context_false_positive
detector_original_verdict                 = split_required
reviewed_verdict                          = split_not_supported
reference_case_status                     = first_review_confirmed
use_as_regression_case                    = true
use_for_detector_performance_estimation   = false
detector_promotion_ready                  = false
```

Sono conservati sezione, frase, riferimento bibliografico, contesto citazionale e
l'assenza dichiarata di metodi, figure e risultati preclinici propri.

Il caso serve come **regressione**, non come stima: un solo esempio non permette
di dichiarare precision, recall o accuratezza, e il rilevatore di produzione non
viene né promosso né modificato.

---

## 10-11. Stato della revisione

| | |
|---|---|
| Prima revisione | **completata** — non clinica, non indipendente |
| Seconda revisione | **necessaria** — nessuna annotazione esiste |
| Gold | `provisional_first_review`, `is_evaluable = false` |
| `second_annotator` · `agreement` · `adjudication` | `null` |

Il `link_status` vive in `first_review_annotation` e non in `final_status`. È la
differenza fra registrare un giudizio e trasformarlo in riferimento: copiarlo nel
gold darebbe al linker una precision misurata contro una sola persona, non
indipendente e non clinica.

**I 70 packet della seconda revisione sono invariati byte per byte**, verificato
prima e dopo, e confrontato anche con gli hash registrati dalla fase precedente.

---

## 12. Limiti

1. La revisione è documentale e non clinica: l'autore non è un clinico.
2. La preparazione è assistita da LLM, quindi la prima revisione non è
   indipendente — ed è precisamente il motivo per cui la seconda serve.
3. Un solo caso non stima le prestazioni del rilevatore.
4. Il rischio residuo della fonte resta di **sottogruppo** e non è stato risolto:
   gli otto sottogruppi sono registrati, non analizzati.
5. Resta aperta l'incoerenza sulla propagabilità rispetto a PMID 22277784
   (sezione 4).

---

## Prossimo passo

**L'approvazione della seconda fonte del batch**, `SOURCE_REVIEW_PMID-22235099.md`
— quella in cui i sistemi preclinici sono quattro e uno ha esito negativo. La
coda standard non riprende in questo branch.
