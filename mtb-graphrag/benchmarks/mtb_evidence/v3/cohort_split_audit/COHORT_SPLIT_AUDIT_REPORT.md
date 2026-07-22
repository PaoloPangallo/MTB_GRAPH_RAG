# Audit strutturale delle coorti — report

## Il risultato in una riga

Il problema di PMID 22277784 **non era isolato**: tre delle nove fonti residue
mescolano evidenza clinica e preclinica, e altre cinque mostrano segnali di più
bracci o più coorti. Solo una delle nove risulta priva di segnali — e anche
quella non può essere dichiarata unità singola, perché di lei abbiamo solo
l'abstract.

---

## Una discrepanza da chiarire subito

La specifica prevedeva **8** unità residue, assumendo che PMID 22277784 fosse fra
le `cohort_partially_resolved` e andasse sottratta.

Non lo era. Era classificata **`insufficient_source_information`** — il bucket
più debole — pur avendo dieci statement. Le residue sono quindi 9, e nessuna
sottrazione era necessaria.

Il conteggio è la parte meno interessante. Il fatto è che la fonte di cui oggi
sappiamo con certezza che contiene una coorte clinica e tre pannelli cellulari
**non era stata segnalata affatto**. Non mancata per poco: proprio non vista.

Prima di questa fase si pensava che il buco riguardasse le fonti a statement
singolo. Riguarda il **canale del segnale**: dieci statement non sono bastati,
perché il segnale non stava lì.

---

## 1-2. Perimetro

**9 unità**, `PU-PMID-22277784-cohort-1` esclusa perché già revisionata e
sostituita. `check_scope` confronta l'insieme derivato con quello dichiarato e
fallisce su qualunque divergenza — un controllo sul numero avrebbe richiesto di
escludere una unità senza motivo.

## 3. Accesso alle fonti

| | |
|---|---:|
| Full text in PMC | **5** |
| Solo abstract | **4** |
| Non accessibili | 0 |

Nessun full text è conservato: viene interrogato in memoria e ne restano hash,
locator e segnali con i loro span.

## 4-9. Classificazione strutturale

| Stato | Unità |
|---|---:|
| `clinical_preclinical_split_required` | **3** |
| `multi_arm_clinical_split_required` | **4** |
| `multi_cohort_clinical_split_required` | **1** |
| `insufficient_source_information` | **1** |
| `single_propagatable_unit` | **0** |
| `partially_separable` · `cohort_not_separable` · `source_unavailable` | 0 |

**Nessuna unità risulta singola e propagabile.** Una lo sarebbe stata sulla base
dell'abstract, ma l'audit ha applicato a sé stesso la lezione: un'assenza di
segnali nel solo abstract non conclude nulla, e quel caso è ora
`insufficient_source_information`.

## 10-11. Proposte di split

**3 proposte · 6 unità derivate proposte · 18 statement rimappati.**

Le proposte esistono solo per lo split clinico/preclinico. È l'unico caso in cui
i segnali delimitano due insiemi disgiunti senza doverli inventare: per bracci e
coorti i segnali dicono *che* esistono, non *quali* siano, e proporre unità
numerate creerebbe partizioni che la fonte non afferma.

Le sei unità proposte portano `unit_type`, `evidence_design` e i candidati
statement. Setting, popolazione, linea e regime restano `unknown`: **l'audit
propone struttura, non contenuto.**

Nessuna proposta è propagabile, nessuna è dichiarata revisionata, tutte sono
`awaiting_first_review` con `cohort_state = candidate_cohort`.

## 12. Regole di propagazione

**12 regole eseguibili con errore tipizzato**, generalizzate dal caso PMID
22277784 e prive di riferimenti a farmaci o studi specifici.

| Regola | Errore |
|---|---|
| `clinical_population_to_model` | `ClinicalToPreclinicalError` |
| `clinical_dimensions_to_model` | `ClinicalToPreclinicalError` |
| `preclinical_setting_to_patients` | `PreclinicalToClinicalError` |
| `model_comparator_to_patients` | `PreclinicalToClinicalError` |
| `cross_cohort_identity` | `CrossCohortError` |
| `cross_arm_intervention` | `CrossArmError` |
| `subgroup_to_population` | `SubgroupToPopulationError` |
| `relative_versus_complete_resistance` | `EvidenceStrengthError` |
| `in_vitro_to_clinical_benefit` | `EvidenceStrengthError` |
| `case_report_to_population` | `EvidenceStrengthError` |
| `mapping_needs_provenance` | `ProvenanceError` |
| `absence_is_not_evidence` | `AbsenceInferenceError` |

**Zero violazioni** sugli artefatti attuali — ma le regole non sono inerti: la
suite le prova una per una su dati deliberatamente scorretti e tutte scattano.

Un bug trovato eseguendole: le regole in forma negativa («il valore c'è ma non
dice X») scattavano sui sentinella, perché `unknown` è truthy e non contiene mai
X. Quattro falsi positivi, corretti.

## 13. Limiti del rilevatore in produzione

`requires_cohort_split` confronta interventi e malattie **fra gli statement**.
Non legge la fonte. Da qui i suoi limiti, che sono di forma e non di
configurazione:

- **non può** vedere una fonte a statement singolo, per costruzione;
- **non può** vedere coorti diverse sotto lo stesso intervento;
- **non può** vedere evidenza clinica e preclinica mescolate;
- **non può** vedere sottogruppi e analisi secondarie.

Rischio di falsi negativi: **alto**. Falsi positivi: basso.

Il rilevatore proposto — 32 segnali, 5 verdetti, deterministico, senza LLM,
indipendente dal numero di statement, con i segnali riportati insieme al verdetto
— **non è promosso in produzione**. È tarato su un solo caso confermato, e
promuoverlo adesso significherebbe generalizzare da un esempio.

## 14. Screening del rischio residuo

Esteso a **tutte e 102 le fonti**, non alle sole 73 a statement singolo: la
specifica lo chiedeva lì, ma PMID 22277784 ne aveva dieci ed era invisibile, e
limitarlo avrebbe riprodotto l'assunzione appena smentita.

| | |
|---|---:|
| Fonti esaminate | 102 |
| A statement singolo | 73 |
| **Candidati allo split** | **43** |
| di cui a statement singolo | 32 |
| **Tasso di rischio residuo** | **42,2%** |

Due verdetti da non leggere come rassicuranti:

- i **6** `insufficient_information` stanno nel bucket in cui era finito
  PMID 22277784, quindi la loro priorità resta media e non bassa;
- i **47** `split_not_indicated` sono **negativi deboli**, formulati sul solo
  abstract. `negative_verdict_is_weak` li marca uno per uno, e
  `verdict_text_basis` mostra che **nessuna** delle 102 fonti è stata valutata sul
  full text.

Il 42,2% è quindi un limite inferiore, non una stima.

## 15. Packet

**9 packet di prima revisione aggiornati** in `first_review_split_audit/`. Gli
originali non sono toccati e ogni packet aggiornato cita quello da cui deriva.

I packet mostrano struttura proposta, unità candidate, statement, dimensioni
condivise e specifiche, avvisi di non propagazione e le domande al revisore.
Non contengono clinical gold, terapie attese, metriche, decisioni finali né
l'esito del pacchetto già revisionato — verificato per assenza di `22277784` e
del nome del primo revisore.

**I 35 packet di seconda revisione sono invariati byte per byte**, e la cosa è
dimostrata: gli hash sono calcolati prima e dopo e confrontati, e un test li
ricalcola dai file per verificare che il controllo non sia obsoleto.

## 16. Metriche

Strutturali, e il campo `metric_kind` lo dichiara nel file perché nessuno le
scambi per metriche di qualità. Precision, recall, F1, accordo, accuratezza
finale e accuratezza di applicabilità clinica restano `not_calculated`: questa
fase non produce revisioni umane e non tocca il gold.

## 17. Readiness

```
cohort_structure_audit_complete   = true
propagation_guards_ready          = true
single_statement_residual_risk    = 0.422
split_proposals_awaiting_review   = 6
ready_to_resume_priority_queue    = true
```

`ready_to_resume_priority_queue` dice una cosa sola: l'audit non lascia sorprese
note a chi riprende le revisioni. Non è readiness per il retrieval qualificato né
per la valutazione finale, che restano `not_ready`.

## 18. Decisioni aperte

1. Le 4 fonti `multi_arm_clinical_split_required` vanno suddivise per braccio, o
   il braccio è la granularità sbagliata quando gli statement non lo distinguono?
2. Il rilevatore source-level va promosso in produzione, e con quale validazione?
3. I 47 negativi deboli vanno rinforzati recuperando il full text, o si accetta
   il rischio dichiarandolo?
4. `insufficient_source_information` deve bloccare la propagazione come fa
   `unresolved_cohort`? Oggi non la blocca.
5. Le 6 unità proposte vanno riviste prima o dopo i pacchetti già in coda?

## 19. Prossimo passo

**Il pacchetto `BA-4c421b7767ebe3d3`** resta il prossimo in coda per rischio di
propagazione — ma l'audit suggerisce di anteporgli le **3 fonti
clinical/preclinical**, per due ragioni.

La prima è che ripetono esattamente il pattern appena risolto su PMID 22277784: il
revisore ha già lo schema di split validato e i packet aggiornati con le unità
candidate, quindi il costo marginale è basso.

La seconda è che è l'unico modo di sapere se il rilevatore proposto funziona. Oggi
è tarato su un caso; tre conferme o tre smentite dicono se merita di andare in
produzione, e quella decisione vale più delle tre revisioni in sé.
