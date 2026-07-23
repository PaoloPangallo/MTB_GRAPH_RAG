# Revisione clinico/preclinica delle tre fonti — report

## Il risultato in una riga

Delle tre fonti che l'audit aveva classificato `clinical_preclinical_split_required`,
**una non contiene alcuna evidenza preclinica**. Le altre due la contengono, e in
una di esse i sistemi preclinici sono quattro anziché uno.

Detto altrimenti: su tre casi, il numero di unità proposto dall'audit era
sbagliato **tre volte su tre** — per eccesso una volta, per difetto due.

---

## 1. Perimetro e accesso

| | |
|---|---:|
| Fonti nel batch | **3** |
| Con full text in PMC | **2** |
| Solo abstract | **1** |
| Locator citati | **23** |
| Locator verificati come corrispondenza esatta | **23** |

Nessun full text è conservato o ridistribuito: i documenti sono stati interrogati
in memoria e ne restano hash, locator, span hash ed estratti brevi.

Su PMID 23344087 il full text non esiste per vie pubbliche — Europe PMC lo
dichiara `Subscription required`, non è in PMC e non è open access. È stato
tentato, non trovato, e la conseguenza è registrata invece che aggirata.
L'abstract recuperato ha però l'hash **identico** a quello che la priority
curation aveva registrato: la fonte su cui si è lavorato è dimostrabilmente la
stessa di allora.

---

## 2. Le tre decisioni

| Fonte | Decisione | Unità: audit → revisione |
|---|---|:-:|
| PMID 22235099 | `audit_split_confirmed_with_more_units` | 2 → **5** |
| PMID 23344087 | `audit_split_partially_supported` | 2 → **3** |
| PMID 31358542 | `audit_split_not_supported` | 2 → **1** |

### PMID 22235099 — quattro sistemi preclinici, non uno

La fonte (Doebele 2012) contiene una coorte clinica di 14 pazienti ALK+
ri-biopsiati alla progressione su crizotinib, 11 con materiale valutabile. Fin
qui l'audit aveva visto giusto.

Quello che non poteva vedere è che la parte preclinica sono **quattro** sistemi
distinti:

1. **Ba/F3** con EML4-ALK wild-type e mutanti G1269A, C1156Y, L1196M — proliferazione e IC50;
2. **NIH3T3** con gli stessi costrutti — colonie in soft agar e immunoblot;
3. **CUTO-1** (derivata dal paziente #10) contro H3122 e H2228 — farmacologia comparativa;
4. **H3122 con KRAS G12V** introdotto, contro vettore vuoto.

Tenerli separati non è pedanteria tassonomica. Il quarto esperimento ha esito
**negativo**: l'IC50 di H3122 con KRAS G12V non è diversa dal controllo, e il
risultato serve agli autori per argomentare *contro* un modello di resistenza.
Fuso in una unica unità «preclinica», quel risultato diventerebbe indistinguibile
dagli altri tre, e un profilo che dicesse «preclinico: resistenza al crizotinib»
affermerebbe l'opposto di ciò che l'esperimento ha mostrato.

### PMID 23344087 — sostenuta, ma non fino in fondo

L'abstract nomina esplicitamente entrambe le componenti: sette pazienti con
resistenza acquisita, e citotossicità in vitro confrontata fra cellule naïve e
resistenti. Lo split è quindi sostenuto.

Non è sostenuta la **composizione** della parte preclinica. L'abstract nomina
SNU-2535 (derivata da un paziente con mutazione G1269), H3122 CR1 come
riferimento, e cloni mutanti L1196M e G1269A — ma non dice su quale fondo
cellulare i cloni siano costruiti, né come si rapportino a SNU-2535. Le tre unità
proposte sono quelle che l'abstract delimita; `preclinical_model_composition`
resta dichiarata **non separabile**.

### PMID 31358542 — il falso positivo

Qui il reperto è netto. Il full text contiene **una sola** occorrenza di
«in vitro», e sta in questa frase:

> «Based on in vitro models, a G1269A/I1171S compound mutation may re-sensitize to
> ceritinib or brigatinib.²³»

È una citazione del lavoro di altri, non un esperimento della fonte. Nessuna
linea cellulare, nessun xenograft, nessun IC50, nessuna trasfezione: la fonte è
uno studio clinico di genotipizzazione su plasma, 84 pazienti e 106 campioni, e
lo split clinico/preclinico proposto **non ha oggetto**.

Il rischio residuo di questa fonte esiste, ma è su un altro asse: otto
sottopopolazioni sovrapposte, e dati riportati per il gruppo aggregato dei TKI di
seconda generazione che è facile attribuire al singolo farmaco.

---

## 3. Unità proposte

| | |
|---|---:|
| Totale | **9** |
| Cliniche | 3 |
| Precliniche | 6 |
| In vitro | 6 |
| In vivo | 0 |

Nessuna delle tre fonti contiene esperimenti in vivo, e il conteggio a zero lo
dice invece di lasciarlo intendere. Il vocabolario dello schema copre comunque
in vivo, xenograft, organoide, farmacologico e molecolare: la fase ha esteso lo
schema perché l'assenza fosse una constatazione e non un limite di
rappresentazione.

**Provenance completeness: 1.000.** Ogni dimensione nota di ogni unità porta il
locator che la sostiene; il costruttore solleva se così non è.

| Campi | |
|---|---:|
| `confirmed` | 32 |
| `unknown` | 36 |
| `not_applicable` | 54 |
| `not_separable` | 4 |

I tre sentinella restano distinti perché dicono cose diverse: `unknown` invita a
cercare ancora, `not_applicable` dice che non c'è niente da cercare (la linea di
terapia di una linea cellulare), `not_separable` dice che cercare non basterebbe.

---

## 4. Statement

Sette statement, tutti `candidate_ambiguous` all'uscita dell'audit.

| Stato | |
|---|---:|
| `candidate_valid` | **1** |
| `candidate_partial` | **4** |
| `candidate_ambiguous` | **2** |

L'unico pienamente valido è `ES-V2-evidence-764`: G1269A osservato in due
pazienti e validato su due sistemi cellulari indipendenti. È anche l'unico caso
in cui osservazione clinica e validazione funzionale coesistono nella stessa
fonte.

Gli altri sono parziali per ragioni che vale la pena nominare una per una:

- `ES-V2-evidence-4288` e `ES-V2-evidence-766` poggiano su **un solo paziente**
  ciascuno (EGFR L858R nel #9, CNG isolato nel #8). Non sono proprietà della
  coorte.
- `ES-V2-evidence-767` poggia sull'unico paziente con copy number gain, che
  portava **anche** EGFR L858R con polisomia elevata: attribuire la resistenza al
  CNG sceglie una delle due spiegazioni senza che la fonte lo faccia.
- `ES-V2-evidence-100003` attribuisce a brigatinib una frequenza che la fonte
  riporta per l'insieme dei TKI di seconda generazione.

### Terminologia

Tre scarti registrati, tutti `requires_terminology_verification`:

| Fonte dice | Statement dice |
|---|---|
| copy number gain (definito come «più del doppio») | ALK **Amplification** |
| ALK gene copy number gain | ALK **Amplification** |
| «less sensitive to crizotinib» | **resistance** |

L'ultimo è il più importante: una riduzione relativa di sensibilità non è una
resistenza, e la distanza fra le due formulazioni cambia che cosa si potrebbe
raccomandare.

---

## 5. Propagazione

**14 regole eseguite su ogni unità, zero violazioni.**

Due regole sono nuove, aggiunte perché nessuna delle dodici esistenti copriva il
loro pattern:

- `cross_model_identity` — `cross_cohort_identity` confronta popolazione, setting
  e linea di terapia, che su un modello sono `not_applicable` e quindi non
  scattano mai;
- `observed_biomarker_to_requirement` — un'alterazione comparsa alla progressione
  promossa a criterio di arruolamento costruisce una coorte mai esistita.

Aggiungerle ha fatto emergere un difetto preesistente: i vocabolari delle unità
cliniche e precliniche erano **riscritti** dentro il modulo delle guardie invece
di venire dallo schema. Ogni tipo di unità aggiunto restava invisibile, e una
unità che le guardie non riconoscono passa tutti i controlli senza che nessuno se
ne accorga.

Un secondo difetto è emerso scrivendo i test: `rule_mapping_needs_provenance`
ispeziona `source_term`, `mapped_term` e `literal_string_present_in_source`, e i
nostri mapping usavano altri nomi. La regola non li guardava affatto. «Zero
violazioni» non significava che i mapping fossero a posto.

Entrambi corretti allineando il produttore al contratto, non indebolendo le
regole.

---

## 6. Il rilevatore

| | |
|---|---:|
| Casi confrontati | 3 |
| Conferme piene | **1** |
| Conferme parziali | **1** |
| Positivi respinti | **1** |
| Fonti col numero di unità corretto | **0** |

Il reperto non è il conteggio ma il meccanismo. Due fonti su tre hanno ricevuto
`split_required` sulla base di **una sola** occorrenza di `preclinical.in_vitro`.
In PMID 23344087 quell'occorrenza sta nei metodi e descrive un esperimento della
fonte; in PMID 31358542 cita i modelli di altri. Stesso segnale, stesso
conteggio, verità opposta.

Il punteggio non separa i due casi: **14 contro 125**, e quello col punteggio più
alto è l'errore.

Non è una soglia da tarare. Il rilevatore non ha nozione di **provenienza dentro
il documento** e non distingue ciò che la fonte fa da ciò che la fonte cita. Il
secondo limite è che nessun segnale conta i modelli distinti: «c'è del
preclinico» non dice mai quanto, e la differenza fra una unità e quattro è quella
fra un profilo usabile e un profilo che fonde quattro esperimenti diversi.

`detector_promotion_ready = false`. La direzione della correzione è però più
utile del verdetto: servono segnali che leggano il contesto dell'occorrenza —
vicinanza a un marcatore di citazione, sezione del documento, presenza di metodi
propri — e un segnale che conti i modelli invece di limitarsi a rilevarne uno.

---

## 7. Stato e blinding

```
review_status                      = source_checked_review_proposal
human_reviewed                     = false
first_review_complete              = false
is_evaluable                       = false
requires_author_approval           = true
requires_second_independent_review = true
is_propagatable                    = false
```

Nessuna proposta è propagabile, e non per una svista fortunata: lo stato
`split_review_proposed` non compare fra quelli propagabili, quindi
`is_propagatable` lo blocca senza casi speciali, e il costruttore solleva se una
proposta risultasse propagabile comunque.

**I 70 file dei packet di seconda revisione sono invariati byte per byte.** Gli
hash sono presi prima del batch, ripresi dopo, confrontati file per file, e un
test li ricalcola dai file per verificare che il controllo non sia obsoleto.
Altri test cercano nei packet ciechi i termini che questa fase ha prodotto — gli
stati, le decisioni strutturali, il nome dello schema — e non li trovano.

Nei packet di approvazione il nome dell'autore non compare: chiedergli di
approvare una proposta che lo cita già come revisore sarebbe una domanda a cui è
già stata data risposta.

---

## 8. Readiness

```
clinical_preclinical_sources_reviewed  = 3
clinical_preclinical_splits_confirmed  = 1
clinical_preclinical_splits_corrected  = 0
clinical_preclinical_splits_rejected   = 1
clinical_preclinical_units_proposed    = 9
author_approvals_pending               = 3
detector_positive_cases_reviewed       = 3
detector_promotion_ready               = false
ready_to_resume_standard_queue         = true
```

`ready_to_resume_standard_queue` dice una cosa sola: il batch non lascia sorprese
note, e il passo successivo è una decisione umana. Non è readiness per il
retrieval qualificato né per la valutazione finale.

---

## 9. Decisioni aperte

1. Ba/F3 e NIH3T3 sono due unità o una sola («modelli isogenici ingegnerizzati»)?
2. L'esperimento con esito negativo su H3122/KRAS G12V va conservato come unità
   propria o come nota della coorte clinica?
3. Su PMID 23344087 si accetta la proposta a tre unità, o si sospende in attesa
   di un accesso al full text che oggi non esiste?
4. `ES-V2-evidence-100003` va declassato a `candidate_invalid`?
5. PMID 31358542 resta unità singola, o le otto sottopopolazioni giustificano uno
   split di sottogruppo — che sarebbe una fase diversa da questa?

---

## 10. Prossimo passo

**L'approvazione dei tre report da parte dell'autore.** Nulla di questa fase può
avanzare senza: le nove unità proposte restano non propagabili, i sette statement
restano candidati, e il gold resta provvisorio.

Il caso da leggere per primo è PMID 31358542, perché è l'unico che chiede una
decisione su qualcosa di più grande di sé: se un positivo del rilevatore possa
essere respinto sulla base di una lettura documentale, e che cosa questo implichi
per i 43 candidati che lo screening dell'audit aveva prodotto con lo stesso
metodo.
