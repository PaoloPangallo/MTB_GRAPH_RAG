# Rigenerazione del qualification corpus — `qualification_corpus/2.0`

**Stato: `ready_for_prototype`.** `migration_id = MIG-V3-002-propagation-policy-and-author-approvals`

---

## 1. Perché una rigenerazione

Il corpus della V3 è stato scritto una volta e poi corretto sette volte, ognuna
in una directory propria: curazione prioritaria, audit strutturale, batch
clinico/preclinico, prima revisione di PMID 22277784, tre approvazioni
dell'autore, normalizzazione della politica di propagazione.

Ogni fase ha fatto la cosa giusta — non riscrivere ciò che l'aveva preceduta — e
il risultato è che **nessun file conteneva lo stato corrente**. Per sapere che
cosa valesse oggi di una unità bisognava leggere otto artefatti e conoscerne
l'ordine, e quell'ordine non era scritto da nessuna parte.

La fase di normalizzazione della politica lo aveva detto esplicitamente:

> «Le altre 99 unità che dichiaravano `true` non vengono riscritte: il loro flag
> è un valore serializzato che il codice non onora più. Ricalcolarlo
> invaliderebbe l'hash del manifest del corpus, che è fuori dal perimetro di
> questa fase.»

Questa è la fase in cui quell'hash cambia.

---

## 2. Le due impronte

La distinzione è la ragione per cui esiste uno schema di manifest nuovo.

```
frozen_kg_snapshot_fingerprint    ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae
                                  invariata — nessun dato è stato scritto nel Knowledge Graph

qualification_corpus_fingerprint  70601662488ba16dea2f416a18156e8886405e08b004cd4308889e065318c104   (1.0)
                              →   99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd   (2.0)

qualified_evidence_snapshot_...   e68520d7f827e7031f45ee74bd0c35a0834ff1fcb61b04cece86a993f0793f2a
                                  derivata da KG + statement + unità + link + gold + policy + schemi
```

La prima identifica il grafo. La seconda identifica ciò che la revisione ne ha
fatto. Chiamare la seconda «nuovo snapshot del KG» direbbe che il grafo è
cambiato, e il grafo non è stato toccato: gli `EvidenceStatement` sono gli stessi
147 byte per byte, con lo stesso `snapshot_fingerprint` nella loro provenienza.

L'impronta è ricalcolabile da chi non ha lo script: `fingerprint_inputs` elenca i
sedici hash che vi entrano, `component_hashes` li riporta, e `non_hashed_fields`
dice quali campi ne restano fuori.

---

## 3. La precedenza, dichiarata

Tredici strati, in ordine di autorità crescente. I rank pari sono **storia** —
fotografie di uno stato precedente — i dispari sono **decisioni**.

| rank | strato | artefatto |
|---|---|---|
| 3 | `qualification_corpus_base` | `qualification_corpus/source_profile_units.jsonl` |
| 4 | `priority_curation_unresolved` | `priority_curation/unresolved_profile_units.jsonl` |
| 5 | `priority_curation_resolved` | `priority_curation/resolved_profile_units.jsonl` |
| 6 | `cohort_split_audit_proposals` | `cohort_split_audit/proposed_profile_units.jsonl` |
| 8 | `clinical_preclinical_review_proposals` | `clinical_preclinical_review_batch/proposed_profile_units.jsonl` |
| 10 | `first_review_22277784_history` | `first_review/superseded_profile_units.jsonl` |
| 11 | `first_review_22277784_units` | `first_review/reviewed_profile_units.jsonl` |
| 12 | `author_approval_31358542_history` | `author_approval/parent_unit_history.jsonl` |
| 13 | `author_approval_31358542_units` | `author_approval/approved_profile_units.jsonl` |
| 14 | `author_approval_22235099_history` | `author_approval_22235099/parent_unit_history.jsonl` |
| 15 | `author_approval_22235099_units` | `author_approval_22235099/approved_profile_units.jsonl` |
| 16 | `author_approval_23344087_history` | `author_approval_23344087/parent_unit_history.jsonl` |
| 17 | `author_approval_23344087_units` | `author_approval_23344087/approved_profile_units.jsonl` |

**Il merge è per campo, non per record.** Uno strato più alto sovrascrive i campi
che dichiara e soltanto quelli: una revisione che decide sul disegno dello studio
non sta dicendo nulla sulla malattia, e trattare il suo silenzio come una
cancellazione perderebbe dati che nessuno ha messo in discussione.

Due strati **allo stesso rank** che propongono valori diversi non vengono risolti
da una regola: la scelta fra due artefatti di pari autorità è un giudizio, e
inventarne uno lo renderebbe invisibile. Il conflitto viene registrato e fa
fallire la rigenerazione. Conflitti trovati: **0**.

`canonical_merge_audit.jsonl` registra per ogni unità quali strati hanno parlato,
quale ha prevalso, quali campi sono stati sovrascritti, quali preservati, e
l'hash di ogni artefatto sorgente.

### Due scelte che sembrano dettagli

**Storia e decisione hanno rank diversi dentro la stessa fase.** Per tre unità di
PMID 22235099 lo stesso id compare in entrambi i file dell'approvazione con
`is_active` opposto. Non è una contraddizione: lo storico fotografa la proposta
*prima* dell'approvazione. Dando allo storico il rank pari e alle unità il
dispari, l'id condiviso si risolve verso l'approvazione e gli id che esistono
solo nello storico restano inattivi — senza casi speciali.

**Le proposte non nascono attive.** Una unità proposta da un audit o da una
verifica documentale è una ipotesi: `is_active` parte da falso, e soltanto una
approvazione la accende. Il contrario avrebbe reso attive sei proposte che
nessuno ha mai approvato.

Le righe di storico contribuiscono **solo i campi di stato**. Lasciarle
contribuire tutto sostituirebbe il record con una fotografia parziale, e
`unit_label` o `note` cancellerebbero valori clinici che nessuno ha discusso.

---

## 4. La migrazione della politica

I sette campi calcolati dalla politica — `cohort_is_resolved`,
`propagation_eligibility`, `may_display_qualifiers`, `is_propagatable`,
`is_hard_filterable`, `is_evaluable`, `requires_second_independent_review` —
non vengono trasportati. Vengono **ricalcolati** per tutte le 123 unità.

`migrate_policy` legge il flag serializzato soltanto per dire se era obsoleto: non
entra nel calcolo. Se entrasse, un dato vecchio potrebbe sopravvivere a una
migrazione che esiste per eliminarlo.

### I 99 flag obsoleti

```
obsolete_serialized_flags_before = 99
obsolete_serialized_flags_after  = 0
```

| artefatto | flag obsoleti |
|---|---|
| `qualification_corpus/source_profile_units.jsonl` | 86 |
| `priority_curation/resolved_profile_units.jsonl` | 13 |

Sono esattamente i due file che la fase di normalizzazione aveva lasciato
indietro, e il numero coincide con quello che quella fase aveva registrato.

Il conteggio si fa **sulle righe come sono scritte su disco**, prima del merge.
Farlo sul record fuso darebbe sempre zero, perché il merge scarta i campi
calcolati dalla politica — e zero non risponde a «quanti dati vecchi c'erano» ma
a «quanti ne ho copiati», che vale zero per costruzione.

`obsolete_serialized_flags.jsonl` elenca le 99 righe con il valore serializzato,
quello ricalcolato e la ragione.

### Distribuzione risultante

| review status | unità |
|---|---|
| `awaiting_source_review` | 65 |
| `awaiting_first_review` | 31 |
| `first_review_complete` | 15 |
| `human_reviewed` | 6 |
| `rejected` | 2 |
| `rejected_as_active_unit_due_to_insufficient_source_resolution` | 2 |
| `replaced_by_author_approved_consolidation` | 2 |

| eligibility | totali | attive |
|---|---|---|
| `none` | 102 | 92 |
| `prototype_only` | 21 | 17 |
| `final` | **0** | **0** |

Zero unità `final`, zero qualificatori hard-filterable. Non è un difetto del
sistema: è lo stato reale della revisione, dove nessun qualificatore ha una
seconda conferma indipendente.

---

## 5. Le quattro revisioni integrate

### PMID 22277784 — prima revisione

Quattro unità attive: una clinica
(`PU-PMID-22277784-clinical-crizotinib-resistant`) e tre precliniche
(`baf3-crizotinib-panel`, `baf3-17aag`, `baf3-next-generation-alk-inhibitors`).
La parent `PU-PMID-22277784-cohort-1` è storica. Locator, decisioni valid/partial,
mapping CH5424802/alectinib non verificato e `relative reduced sensitivity`
sopravvivono nelle decisioni e nei mapping. Tutte e quattro `prototype_only`, non
propagabili, non hard-filterable, non valutabili.

### PMID 31358542 — split respinto

Una sola unità clinica attiva. Le due proposte dell'audit —
`clinical-component` e `preclinical-component` — restano storiche e inattive.
Nessuna unità preclinica attiva esiste per questa fonte. Gli otto sottogruppi
restano attributi dell'unità e non diventano unità.
`ES-V2-evidence-100003 = candidate_invalid`,
`ES-V2-evidence-100004 = candidate_partial`. Il caso del rilevatore resta un hard
negative da citation context.

### PMID 22235099 — split confermato con più unità

Quattro unità attive: coorte clinica, modelli isogenici ingegnerizzati (due
`model_instances`), CUTO-1 patient-derived, esperimento negativo H3122/KRAS G12V.
`baf3-engineered` e `nih3t3-engineered` restano storiche con
`replaced_by_author_approved_consolidation`.

L'esperimento negativo conserva `assertion_polarity = does_not_support` e non
aggiunge alcuna dimensione ai suoi tre link: non può diventare un supporto
positivo per costruzione, non per convenzione. CUTO-1 conserva
`derived_from_clinical_case = patient_10`, `derivation_is_identity = false`,
`biomarker_requirements = []` e `cross_context_biomarker_propagation = forbidden`.

`ES-V2-evidence-764 = candidate_valid`, `ES-V2-evidence-4288 = candidate_partial`
case-level, `ES-V2-evidence-766 = candidate_partial` named-patient-subset con
`patient_7` e `patient_8`. Il mapping copy-number gain / amplification resta non
verificato.

### PMID 23344087 — split parzialmente sostenuto

Due unità attive: coorte clinica e pannello preclinico non risolto.
`engineered-clones` e `patient-derived` restano storiche e inattive con
`rejected_as_active_unit_due_to_insufficient_source_resolution` e
`rejected_as_false = false` — non sono sbagliate, sono non verificabili, e il
full text potrebbe riattivarle.

Il pannello conserva `preclinical_model_composition = not_separable`,
`component_to_statement_mapping = not_separable`,
`cellular_background_of_mutant_clones = unknown`, `source_basis = abstract_only`,
`structural_confidence = partial`, `full_text_verified = false`.
`ES-V2-evidence-765 = candidate_partial` con `relative_reduced_sensitivity`,
`ES-V2-evidence-767 = candidate_ambiguous` case-level con EGFR L858R co-occorrente
e `causal_attribution = not_separable`.

---

## 6. Link e viste

**201 link**, tutti verso le 109 unità attive. Zero link verso le 14 storiche: una
parent sostituita resta nel corpus perché la storia sia leggibile, e proprio per
questo non deve comparire in una vista — chi la trovasse fra i qualificatori non
avrebbe modo di sapere che descrive uno stato superato.

**147 viste**, una per statement, in modalità `prototype`. La modalità non è una
etichetta: determina tre cose.

- I qualificatori `none` **non vengono applicati**. Nessuno li ha confermati, e
  mostrarli li renderebbe indistinguibili da quelli letti su una fonte.
- I qualificatori `prototype_only` vengono applicati e **mostrati**, con
  `display_allowed = true` e `hard_filter_allowed = false`. Nasconderli
  toglierebbe a chi può correggerli l'unica occasione di vederli.
- Nessuna dimensione è hard-filterable, perché nessuna unità è `final`.

Ogni campo aggiunto espone valore, unità di origine, identificatore della fonte,
locator, stato di revisione, eligibility, se può essere mostrato, se può filtrare,
e la provenienza completa. I campi nativi degli `EvidenceStatement` non vengono
toccati: `native_fields_overwritten = false`, e un test confronta il
`base_statement` con l'originale dell'adapter.

### Le tre assenze restano distinte

`unknown`, `not_applicable` e `not_separable` hanno campi propri nella vista, e
`sentinel_sources` dice quale unità ha prodotto quale. Non sono sinonimi: dicono
rispettivamente che nessuno lo sa, che la domanda non si pone, e che la fonte
conferma i componenti ma non la loro relazione.

### Le quattro verifiche di non-propagazione

| verifica | esito |
|---|---|
| 31358542 non produce link preclinici attivi | nessuna unità preclinica attiva |
| 22235099 non propaga il negativo come resistenza | `does_not_support`, zero dimensioni aggiunte |
| 23344087 non separa componenti non verificabili | due campi `not_separable` su ogni link del pannello |
| 22277784 non propaga la popolazione ai modelli | conflitto registrato, dimensione non applicata |

L'ultima merita una riga. Lo statement `ES-V2-evidence-100005` è collegato sia
alla coorte clinica sia ai tre modelli Ba/F3. La coorte porta «18 patients with
ALK-positive NSCLC», i modelli portano «engineered Ba/F3 cell models». La vista
trova due valori diversi per `population` e **non applica la dimensione**: la
registra come conflitto, perché scegliere fra due fonti revisionate è un giudizio
umano e non una regola di precedenza.

---

## 7. Gold provvisorio

94 record, invariati rispetto alla versione della fase precedente. 17 portano una
annotazione di prima revisione — dieci da PMID 22277784, due da 31358542, tre da
22235099, due da 23344087: il gold accumula, non sostituisce.

```
final_status      = provisional_first_review
is_evaluable      = false
second_annotator  = null
agreement         = null
adjudication      = null
```

Nessuna decisione candidate è copiata in `final_status`, e un validatore lo
verifica su tutti e 94 i record.

---

## 8. Diff e criteri di accettazione

142 differenze, tutte classificate.

| classe | numero |
|---|---|
| `expected_policy_migration` | 87 |
| `expected_history_update` | 27 |
| `expected_unit_restructure` | 22 |
| `expected_author_approval` | 5 |
| `expected_hash_change` | 1 |
| **`unexpected_change`** | **0** |
| **`unresolved_conflict`** | **0** |

Con `obsolete_serialized_flags_after = 0`, i tre cancelli di accettazione sono
tutti a zero. Lo schema del manifest lo impone: un manifest
`ready_for_prototype` con uno dei tre diverso da zero non valida.

Lo stato **non** è `frozen`, e non può esserlo: manca la seconda revisione, il
gold non è valutabile, non esistono unità `final`, e il corpus è destinato al
prototipo.

---

## 9. Determinismo

- due rigenerazioni producono file identici byte per byte;
- gli artefatti committati coincidono con una esecuzione fresca su directory
  temporanea;
- **leggere gli strati in ordine inverso produce lo stesso risultato.** Se non lo
  facesse, la precedenza dipenderebbe dall'ordine di lettura e non sarebbe una
  precedenza;
- nessun timestamp e nessun path di macchina entra negli hash: `generated_at`,
  `created_at`, `reviewed_at`, `access_date`, `review_date` e
  `reverse_input_order` sono dichiarati in `non_hashed_fields`.

L'ultimo campo è stato aggiunto perché un test è fallito. `reverse_input_order`
finiva in `qualification_scope.json` e quindi nell'hash dello scope, e quindi nel
fingerprint del corpus: l'impronta dipendeva da come lo script era stato
invocato, che è esattamente la proprietà che la rigenerazione esiste per
escludere.

---

## 10. Immutabilità

I 70 packet ciechi della seconda revisione sono byte-identical, e il loro hash
aggregato entra nel fingerprint del corpus. Restano invariati anche gli artefatti
originali di curazione prioritaria, audit strutturale, batch clinico/preclinico,
prima revisione, tre approvazioni e politica di propagazione. La nuova versione
li **cita** — `previous_corpus_directory`, `previous_corpus_manifest`,
`source_artifact_hashes` nell'audit di merge — e non li riscrive.

I 99 flag obsoleti sono ancora là dove erano: sparire dal corpus nuovo è una cosa
diversa dal riscriverli retroattivamente, e un test verifica che le 86 unità del
corpus precedente dichiarino ancora `is_propagatable = true`.

Una nota sul blinding. Il termine `candidate_ambiguous` **compare** nei packet
ciechi, e non è una violazione: è la classificazione automatica prodotta prima di
ogni revisione umana, etichettata come `automatic_classification`. Il test cerca
ciò che soltanto una decisione di prima revisione porta con sé — un revisore, una
annotazione, un livello di propagazione — e un secondo test verifica che quel
campo resti etichettato automatico.

---

## 11. Una lacuna registrata e non chiusa

Le guardie di propagazione trovano **10 unità attive** che dichiarano
`biomarker_requirements` senza `biomarker_role`. Non le ha introdotte questa
fase: sono unità scritte prima che la regola `observed_biomarker_to_requirement`
esistesse — quattro dalla prima revisione di PMID 22277784, sei dal corpus base.

`guard_findings.jsonl` le registra come `pre_existing_gap` non bloccante, e la
readiness porta `biomarker_role_backfill_required = true`.

Riempire il campo a posteriori significherebbe decidere al posto di un revisore
che non ha deciso; ometterlo nasconderebbe una lacuna reale. Le sei unità del
corpus base hanno eligibility `none` e non entrano nemmeno nelle viste; le quattro
di PMID 22277784 sono `prototype_only` e vi entrano, quindi la lacuna è visibile
dove conta.

---

## 12. Metriche

Solo descrittive. Nessuna misura la qualità del sistema.

| | |
|---|---|
| EvidenceStatement | 147 |
| fonti | 102 |
| unità totali | 123 |
| unità attive | 109 |
| unità storiche | 14 |
| unità prototype-visible | 17 |
| unità final-propagatable | 0 |
| qualificatori hard-filterable | 0 |
| flag obsoleti rimossi | 99 |
| link | 201 |
| viste prototipo | 147 |
| record di gold | 94 |
| fonti con prima revisione completa | 4 |
| unità unresolved | 17 |
| unità abstract-only | 2 |
| statement case-level | 2 |
| statement named-patient-subset | 1 |
| esperimenti negativi | 1 |
| mapping terminologici pendenti | 6 |
| conflitti | 53 |
| ambiguità | 1 |
| campi not-separable | 4 |

Non calcolate: linking precision, recall, F1, agreement, detector accuracy,
clinical applicability accuracy, final retrieval quality. Nessuna seconda
revisione esiste, nessuna unità è `final` e il gold non è valutabile: una metrica
di qualità calcolata qui misurerebbe il sistema contro se stesso.

---

## 13. Prossimo passo

Implementazione del prototipo `QualifiedEvidenceRetriever`. Le condizioni sono
descritte in `QUALIFIED_RETRIEVER_READINESS.md`; in breve: può leggere e mostrare,
non può filtrare.
