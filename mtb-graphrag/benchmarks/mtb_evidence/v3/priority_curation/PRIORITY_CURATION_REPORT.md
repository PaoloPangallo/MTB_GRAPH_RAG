# Curation prioritaria delle fonti — report

Una avvertenza prima dei numeri, perché cambia come vanno letti tutti.

Questa fase ha aggiunto **verifica della fonte e struttura delle coorti**, non
qualificatori clinici. L'unica dimensione che guadagna copertura è
`evidence_design`, da 54 a 60 unità. Setting, linea di terapia, stadio e
popolazione restano a 6, esattamente dove erano.

Non è un fallimento dell'esecuzione: è il risultato di aver rifiutato di emettere
valori che l'abstract non dimostra. La sezione «Perché la copertura clinica non è
cresciuta» spiega il caso concreto che ha determinato la scelta.

---

## Quattro livelli da non confondere

Il report li tiene separati ovunque, perché collassarli è il modo più semplice di
far sembrare revisionato ciò che non lo è.

| Livello | Che cosa significa | Quantità |
| --- | --- | ---: |
| **curation automatica** | valore prodotto da estrazione deterministica ancorata a span | 13 valori |
| **verifica della fonte** | l'abstract è stato recuperato e consultato | 34 unità |
| **revisione umana** | una persona ha letto la fonte e confermato | 4 unità, tutte preesistenti |
| **gold** | verdetto di riferimento su un collegamento | **0** |
| **prediction** | proposta del linker | 94 |

---

## 1-3. Perimetro

**35 unità prioritarie.** Non 45: i due gruppi non sono disgiunti.

| Gruppo | Unità |
| --- | ---: |
| A — coorte irrisolta | 16 |
| B — multi-statement | 29 |
| **A ∩ B** | **16** |
| solo A | 0 |
| solo B | 13 |
| solo conflitto | 6 |
| **totale** | **35** |

**A è interamente contenuto in B**, e la relazione è strutturale, non empirica.
`requires_cohort_split` confronta interventi e malattie *fra gli statement* di una
fonte, quindi non può accendersi su una fonte con un solo statement. Una
pubblicazione a statement singolo che descrive due coorti resta invisibile a
questo rilevatore. È un punto cieco noto, e non è stimabile con i dati attuali.

Le 6 unità conflittuali fuori da A e B sono state incluse benché l'obiettivo le
chiedesse solo dentro A o B: un conflitto è il caso di propagazione più
pericoloso già noto, e includerlo costa solo lavoro.

## 4. Fonti accessibili

**34 su 35** hanno un abstract recuperato da PubMed. Una — PMID 26181354 — non
espone abstract nel record del registro ed è marcata `awaiting_source_access`.

## 5-8. Coorti

| Stato | Unità |
| --- | ---: |
| `cohort_resolved` | **10** |
| `cohort_partially_resolved` | **9** |
| `insufficient_source_information` | **15** |
| `source_unavailable` | **1** |
| `cohort_not_separable` | 0 |

**Nessuna unità nuova è stata creata.** Le 9 fonti multi-braccio sono
riconosciute — l'abstract dice che le coorti esistono — ma non permettono di
assegnare ciascuno statement alla propria. Suddividere sulla base degli statement
del sistema creerebbe coorti che la fonte non afferma, cioè esattamente la
fabbricazione che il protocollo vieta.

I 15 `insufficient_source_information` meritano attenzione: gli statement
attribuiscono a quelle fonti più interventi o più malattie, ma l'abstract non
contiene marcatori di struttura. L'assenza di marcatori **non** dimostra che la
coorte sia unica, quindi lo stato non è `cohort_resolved`.

## 9. Fonti multi-intervento

**14 su 35.**

## 10-14. Classificazione dei collegamenti candidati

| Classe | Coppie |
| --- | ---: |
| `candidate_valid` | **34** |
| `candidate_partial` | 1 |
| `candidate_ambiguous` | **12** |
| `candidate_conflicting` | **7** |
| `candidate_invalid` | **0** |
| `candidate_not_determinable` | **40** |

Tipo di supporto: 46 `direct_support`, 1 `indirect_support`, 47
`unsupported_by_primary_source`.

Lo zero su `candidate_invalid` è deliberato. Quando un intervento non compare
nell'abstract, la classificazione è `candidate_not_determinable`, non «invalido»:
un abstract non nomina tutto ciò che il full text contiene, e dedurre la falsità
della claim dall'assenza sarebbe un errore più grave di quello che eviterebbe.

I 12 `candidate_ambiguous` sono casi in cui l'intervento **è** in una sezione
primaria ma la coorte non è risolta: si sa che la fonte parla di quel farmaco,
non a quale braccio lo statement appartenga.

## 15-16. Campi aggiunti e ancora ignoti

Emessi come valore: **13** (`evidence_design`).

Rilevati ma **non emessi**, diventati domande per il revisore con lo span
allegato: 11 `setting`, 11 `therapy_line`, 1 `stage`, 1 `resection_status`.

Rilevazioni discordanti, nessun valore proposto: 6 `evidence_design`, 2
`setting`, 1 `therapy_line`.

## 17. Copertura prima e dopo

| Dimensione | Prima | Dopo | human | source_checked | machine |
| --- | ---: | ---: | ---: | ---: | ---: |
| `evidence_design` | 54 | **60** | 0 | 20 | 40 |
| `setting` | 6 | 6 | 6 | 0 | 0 |
| `stage` | 6 | 6 | 6 | 0 | 0 |
| `therapy_line` | 6 | 6 | 6 | 0 | 0 |
| `population` | 6 | 6 | 6 | 0 | 0 |
| `prior_therapies` | 6 | 6 | 6 | 0 | 0 |
| `biomarker_requirements` | 6 | 6 | 6 | 0 | 0 |
| `regimen` | 6 | 6 | 6 | 0 | 0 |
| `disease` | 6 | 6 | 6 | 0 | 0 |
| `intervention` | 5 | 5 | 5 | 0 | 0 |
| `inclusion_criteria` | 6 | 6 | 6 | 0 | 0 |
| `exclusion_criteria` | 4 | 4 | 4 | 0 | 0 |
| `comparator` | 0 | 0 | 0 | 0 | 0 |
| `resection_status` | 0 | **0** | 0 | 0 | 0 |

Le colonne `human` e `source_checked` restano separate. Un valore estratto da uno
span dell'abstract non è un valore letto da una persona, e presentarli insieme
farebbe sembrare revisionato ciò che non lo è.

### Perché la copertura clinica non è cresciuta

Il motore di estrazione, applicato senza filtro, produceva valori. Sul PMID
15329413 — Pao et al., mutazioni EGFR nei non fumatori — le regex hanno estratto:

- `resection_status = resected`, da «15 adenocarcinomas **resected** from untreated never smokers»;
- `therapy_line = relapsed or refractory`, da «gefitinib-**refractory** tumors».

Entrambi plausibili. Entrambi sbagliati: descrivono i campioni tumorali, non il
disegno dello studio. E nessuno dei due sarebbe stato distinguibile da un valore
giusto guardando il file.

Da lì la regola: solo `evidence_design` diventa un valore, perché i marcatori di
fase, randomizzazione e preclinico descrivono davvero lo studio. Le altre quattro
dimensioni restano rilevate, allegate al packet con lo span, e il campo resta
`unknown`.

Il costo è una copertura clinica ferma. Il beneficio è che ciò che il corpus
contiene resta vero.

### Un guadagno collaterale

7 fonti precliniche sono ora identificate — 6 `in vitro`, 1 `cell lines` — da
un'**affermazione diretta** nell'abstract, non dall'assenza di marcatori clinici.
Chiude la categoria che la fase precedente aveva dichiarato scoperta.

## 18. Provenance completeness

**1.000.** Ogni dimensione nota di ogni unità curata porta pattern, sezione,
offset, testo esatto, data di accesso e hash del testo sorgente.

## 19-20. Stato delle revisioni

**Prima revisione: 35 packet prodotti, 0 completate.**
**Seconda revisione: 35 packet prodotti, 0 completate.**

Nessun annotatore è stato simulato. `agreement` è `null`, non `0.0`.

I packet di seconda revisione non contengono la decisione della prima, e i loro
identificatori sono derivati con un salt così da non essere allineabili. La mappa
fra i due round esiste per l'adjudication ed è marcata come da non consegnare ai
revisori.

## 21. Decisioni cliniche aperte

1. Le 9 fonti a `cohort_partially_resolved` vanno suddivise leggendo il full
   text, oppure trattate come non separabili in via definitiva?
2. Sui 15 `insufficient_source_information`, quale evidenza minima serve per
   dichiarare una coorte unica?
3. `Cholangiolocellular Carcinoma` e `cholangiocarcinoma` sono la stessa entità ai
   fini della qualificazione? Il conflitto resta aperto dalla fase A.
4. Una fonte citata da uno statement ma che non nomina l'intervento nel full text
   va classificata `invalid` o resta `not_determinable`?
5. `indirect_support` è sufficiente a qualificare uno statement, o solo a
   sostenerlo debolmente?
6. Quale copertura minima di `setting` e `therapy_line` rende utile un filtro
   contestuale invece che rumoroso?

## 22. Readiness per dimensione

In [`QUALIFIED_RETRIEVAL_READINESS.md`](QUALIFIED_RETRIEVAL_READINESS.md).

Sintesi: `ready` su malattia, intervento, direzione e polarità (native negli
statement); `partially_ready` su `evidence_design`; `blocked_by_review` su
setting, linea, stadio e resezione — i dati sono pronti, manca la conferma;
`not_ready` sulle restanti.

```
ready_for_prototype_retrieval = true
ready_for_final_evaluation    = false
```

## 23. Rischio residuo di propagazione

**Basso su ciò che il sistema propaga oggi, alto su ciò che non vede.**

6 prediction su 94 hanno avuto dimensioni soppresse perché la coorte non è
risolta: il link resta, la propagazione no. 2 prediction su 94 sono
`conflicting_match` e non propagano nulla.

Il rischio residuo vero è il punto cieco: una fonte a statement singolo che
descrive più coorti non viene mai marcata come multi-coorte, quindi
propagherebbe senza che nulla la fermi. Nessuna delle 35 unità esaminate è in
questa condizione — ma il perimetro è stato costruito con lo stesso rilevatore
che ha il punto cieco, quindi l'assenza non è una prova.

`ambiguous_qualification_rate` sale da 0.157 a 0.216. È un miglioramento che si
presenta come un numero peggiore: più unità sono ora correttamente marcate come
non risolte, invece di sembrare risolte per difetto di rilevazione.

## 24. Prossimo passo

**Prima revisione umana sui primi 10 packet della coda**, ordinati per rischio di
propagazione. Sono le unità dove un errore si moltiplicherebbe su più
proposizioni.

Il lavoro è già preparato: gli span sono individuati, le domande sono formulate,
e per setting e linea di terapia il revisore deve confermare o smentire una
rilevazione precisa invece di leggere l'intero abstract al buio.

Solo dopo, la seconda revisione e la misura dell'accordo. Prima di quella, nessuna
metrica di linking è difendibile.
