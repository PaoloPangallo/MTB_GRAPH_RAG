# V3 — Qualification corpus

Questo documento descrive il corpus di qualificazione costruito sopra i 147
`EvidenceStatement` congelati: come sono state scelte le fonti, che cosa e' una
unita' di annotazione, quali stati di revisione esistono e perche' il corpus
**non** e' ancora congelato.

Una avvertenza che vale per tutto il resto. Il corpus prodotto in questa fase e'
un'**infrastruttura di annotazione completa con sei unita' annotate su 102**.
Non e' un corpus annotato. Ogni numero qui sotto va letto sapendolo.

---

## 0. Mappa dei componenti reali

| Componente | File | Responsabilita' | Riuso | Modifica |
| --- | --- | --- | --- | --- |
| `SourceIdentity` | `backend/pipeline/evidence/source_identity.py` | normalizza PMID/DOI/NCT, decide quando due riferimenti sono la stessa fonte | nuovo, si appoggia a `audit_lib.normalize` | — |
| `SourceClinicalProfileUnit` | `backend/pipeline/evidence/profile_unit.py` | unita' di annotazione per coorte | nuovo | — |
| `StatementQualificationGold` | `backend/pipeline/evidence/qualification_gold.py` | verdetto di riferimento sui link | nuovo | — |
| `QualificationCorpusManifest` | `backend/pipeline/evidence/corpus_manifest.py` | hash e guardie di freeze | nuovo | — |
| `EvidenceStatementRepository` | `backend/pipeline/evidence/repository.py` | i 147 statement | **riusato invariato** | nessuna |
| `EvidenceQualificationLink` | `backend/pipeline/evidence/qualification.py` | linker corrente | **riusato invariato** | nessuna |
| `QualifiedEvidenceView` | `backend/pipeline/evidence/qualification.py` | vista derivata | **riusato invariato** | nessuna |
| `SourceClinicalProfile` | `benchmarks/mtb_evidence/evaluation/contracts.py` | profili annotati a mano | **riusato invariato** | nessuna |
| `REVIEWED_PROFILES` | `benchmarks/mtb_evidence/evaluation/reviewed_profiles.py` | gli otto profili revisionati | **riusato invariato** | nessuna |
| `norm_pmid` / `norm_nct` | `benchmarks/mtb_evidence/pilot/audit_lib/normalize.py` | normalizzazione validata dall'audit | **riusato** | nessuna |
| inventario | `benchmarks/mtb_evidence/evaluation/source_inventory.py` | censimento delle fonti | nuovo | — |
| scope, unita', packet | `benchmarks/mtb_evidence/evaluation/corpus_builder.py` | costruzione del corpus | nuovo | — |
| valutazione del linking | `benchmarks/mtb_evidence/evaluation/linking_evaluation.py` | metriche contro il gold | nuovo | — |

Nessun file del frontend, nessun `.tex`, nessuna scrittura su Neo4j.

---

## 1. Universo di selezione

L'universo e' definito **dai 147 `EvidenceStatement` congelati**, non dal clinical
gold.

La differenza decide la validita' dell'intero esperimento. Partire dal gold
significherebbe annotare le fonti che gia' sappiamo essere rilevanti, e misurare
poi quanto bene il sistema le ritrova — cioe' misurare quanto bene sappiamo la
risposta. Partire dagli statement significa annotare cio' che il sistema ha
davvero in mano, incluse le fonti che lo contraddicono.

Risultato: **102 fonti uniche**, 147/147 statement coperti.

---

## 2. Prevenzione del bias

La strategia di selezione e' un **censimento**: tutte le 102 fonti entrano nel
corpus. Nessuna esclusione discrezionale, perche' non esiste un criterio da cui
una fonte scomoda possa essere esclusa.

E' una scelta piu' forte di un campionamento stratificato. Uno stratificato
richiede di fidarsi che i pesi non siano stati scelti guardando i risultati; un
censimento rende la domanda priva di oggetto.

Gli strati esistono comunque, ma come **etichette di copertura**, non come
filtri. Servono a verificare che il corpus contenga anche cio' che al sistema
farebbe comodo non avere:

| Strato | Fonti |
| --- | ---: |
| entrate nel retrieval del pilot | 89 |
| citate in un report | 19 |
| terapia nominata nel report | 58 |
| citate senza essere nel retrieval | 0 |
| sensibilita' | 72 |
| resistenza | 31 |
| polarita' negativa (`does_not_support`) | 4 |
| scope non terapeutico | 49 |
| conflitto di malattia noto | 7 |
| multi-statement | 29 |
| multi-intervento | 14 |
| multi-malattia | 9 |
| identificate da DOI | 1 |
| presenti come nodo | 3 |
| solo `citation_only` | 85 |
| presenza ignota | 14 |

Lo strato `unsupported_report_citation` vale **0**, ed e' un reperto positivo:
nessun report del pilot ha citato una fonte che il retrieval di quel caso non
avesse fornito. E' calcolato senza il clinical gold, proprio per non introdurlo
dalla porta di servizio.

---

## 3. Source inventory

Per ogni fonte l'inventario registra identificatori normalizzati, titolo,
statement e record del grafo associati, casi, malattie, biomarcatori, interventi,
direzioni, scope, polarita', livelli, presenza nello snapshot, profilo
disponibile, strati, sospetta suddivisione in coorti e priorita' di annotazione.

**Identita' delle fonti.** Due riferimenti sono la stessa fonte se e solo se
condividono almeno un identificatore controllato normalizzato. Il titolo non
partecipa mai alla decisione.

L'asimmetria e' voluta. Un falso negativo lascia due unita' separate che un
revisore puo' unire in un minuto. Un falso positivo fonde due studi diversi e
propaga i qualificatori clinici dell'uno sugli statement dell'altro, producendo
una qualificazione sbagliata che nessuna metrica a valle distingue da una
giusta. `titles_are_similar` esiste, e' esposta, ed e' deliberatamente **mai
chiamata** dal resolver: serve a segnalare a un revisore che due fonti
*potrebbero* coincidere, non a deciderlo.

**Presenza nello snapshot.** `node`, `citation_only`, `absent` e `unknown` restano
distinti. Una fonte `citation_only` compare dentro `Evidence.citation_id` ma non
esiste come nodo `Publication`: un retriever che la trattasse come nodo
troverebbe zero risultati senza segnalare nessun errore.

---

## 4. Unita' di annotazione

`SourceClinicalProfile` assume implicitamente **una pubblicazione = un profilo**.
L'assunzione regge finche' la fonte descrive un braccio solo, e cade appena
descrive due coorti con linee di terapia diverse — il caso normale in oncologia.
Con un profilo unico i qualificatori delle due coorti si fondono, e uno statement
eredita il setting dell'altro braccio. L'errore e' invisibile: il risultato resta
un profilo sintatticamente valido.

`SourceClinicalProfileUnit` sposta l'unita' sulla **coorte**:

```
source + cohort + intervention/regimen + biomarker + disease context
```

Una fonte a braccio unico ha esattamente una unita', quindi il caso semplice non
paga il costo del caso complesso.

Quando le coorti esistono ma i dati disponibili non permettono di separarle,
l'unita' resta `unresolved_cohort`: non si sceglie una coorte a caso, non si
fondono i qualificatori, e `is_propagatable` diventa `False`. **16 unita' su 102**
si trovano in questo stato.

---

## 5. Fonti ammesse

In ordine di preferenza: artefatti gia' presenti nel repository, profili gia'
revisionati, abstract e metadati PubMed, record ClinicalTrials.gov, full text
pubblicamente accessibile, documentazione regolatoria primaria.

Non ammessi: blog, aggregatori non verificati, riassunti generati da motori di
ricerca, output di LLM, il clinical gold, le prediction della pipeline.

**Che cosa e' stato effettivamente recuperato.** Solo metadati bibliografici da
PubMed E-utilities, in cache versionata: titolo, rivista, anno, tipi di
pubblicazione. Da questi si ricava un solo campo clinico, `evidence_design`, e
solo perche' il tipo di pubblicazione e' **asserito dal registro**.

Setting, stadio, linea di terapia, popolazione, terapie precedenti, criteri e
stato di resezione restano `unknown`. Dedurli dal titolo o dall'abstract
produrrebbe profili plausibili e non verificati, che e' la cosa peggiore che
questo corpus possa contenere: un valore sbagliato non si distingue da uno giusto
guardando il file.

Per la stessa ragione l'assenza di un tipo di pubblicazione clinico produce
`not_determinable_from_registry` e **non** `preclinical`: il registro non
autorizza quell'inferenza.

---

## 6. Stati di revisione

`unreviewed` · `machine_extracted` · `source_checked` · `awaiting_source_review` ·
`awaiting_first_review` · `first_review_complete` · `awaiting_second_review` ·
`second_review_complete` · `disagreement` · `adjudicated` · `frozen` · `rejected` ·
`human_reviewed`

Il processo automatico puo' produrre `machine_extracted`, `source_checked` e i
packet. Non puo' dichiarare `first_review_complete`, `second_review_complete`,
`adjudicated`, `frozen` o `human_reviewed`: `validate_units` lo rifiuta, e il
motivo e' che un automatismo che si dichiara revisionato trasforma la propria
estrazione in gold.

Stato attuale: **6 unita' `human_reviewed`** — quelle degli otto profili
preesistenti, conservate invariate — e **96 `awaiting_source_review`**.

---

## 7. Doppia annotazione

Il workflow e':

```
coppie candidate → annotazione cieca 1 → annotazione cieca 2
                 → verifica di accordo → adjudication → gold → freeze
```

I packet sono ciechi per costruzione: non contengono il clinical gold, le terapie
attese, le metriche del sistema, lo strato della fonte, la priorita' di
annotazione ne' una decisione KEEP/AMEND/REJECT. Anche il `blind_annotation_id` e'
un hash, cosi' che l'identificatore non riveli quale fonte pesa di piu'.

L'accordo si calcola **solo** dove esistono due annotazioni di due annotatori
diversi. `has_two_real_reviews` controlla anche che gli identificatori
differiscano: senza quel controllo, la stessa annotazione ripetuta produrrebbe un
accordo perfetto privo di significato.

Quando le due revisioni non ci sono, `agreement` vale `None` e non `False`, e
`agreement_rate` restituisce `(None, 0)` e non `0.0`. Uno 0.0 verrebbe letto come
«gli annotatori non sono mai d'accordo» invece che «non esistono due annotatori».

**In questa fase la seconda revisione non e' stata prodotta.** Il gold e' quindi
provvisorio, non congelato, e nessun accordo viene calcolato.

---

## 8. Adjudication

Un disagreement richiede un adjudicator nominato: `StatementQualificationGold`
solleva un errore se esiste una `adjudication` senza `adjudicator`, perche' un
verdetto non attribuibile a nessuno non e' verificabile.

L'adjudication vince sulle due annotazioni e determina `final_status`.

---

## 9. Link gold

`StatementQualificationGold` registra la coppia statement-unita', le due
annotazioni, l'accordo, l'adjudication, le dimensioni applicabili, escluse, in
conflitto e ambigue, i codici di motivazione e i locator.

`link_status` ammette: `valid_link`, `partial_link`, `ambiguous_link`,
`conflicting_link`, `invalid_link`, `no_profile_available`, `source_missing`,
`insufficient_source_information`.

---

## 10. Candidate link e gold

Sono due tipi distinti, e la distinzione e' la ragione d'essere del modulo.

Il linker propone **candidati**. Se quei candidati diventassero il gold, la
valutazione misurerebbe la coerenza del linker con se stesso e restituirebbe
precision 1.000 qualunque cosa il linker faccia.

`candidate_from_link` conserva la prediction **nella nota**, dove e' leggibile ma
inerte: non popola nessuna annotazione, quindi non puo' diventare per errore il
riferimento contro cui il linker viene misurato. Il record resta in stato
`candidate`, `is_evaluable` e' `False` e `final_status` e' la stringa vuota —
deliberatamente vuota invece che ottimistica, perche' un gold provvisorio che
esponesse un verdetto verrebbe usato come se fosse definitivo.

---

## 11. Metriche

**Copertura per dimensione** (unita' su 102):

| Dimensione | frozen KG | profilo revisionato | machine-extracted | ancora unknown |
| --- | ---: | ---: | ---: | ---: |
| `disease` | 0 | 6 | 0 | 96 |
| `biomarker_requirements` | 0 | 6 | 0 | 96 |
| `intervention` | 0 | 5 | 0 | 97 |
| `regimen` | 0 | 6 | 0 | 96 |
| `population` | 0 | 6 | 0 | 96 |
| `stage` | 0 | 6 | 0 | 96 |
| `setting` | 0 | 6 | 0 | 96 |
| `therapy_line` | 0 | 6 | 0 | 96 |
| `prior_therapies` | 0 | 6 | 0 | 96 |
| `inclusion_criteria` | 0 | 6 | 0 | 96 |
| `exclusion_criteria` | 0 | 4 | 0 | 98 |
| `evidence_design` | 0 | 0 | 54 | 48 |
| `comparator` | 0 | 0 | 0 | 102 |
| `resection_status` | 0 | 0 | 0 | 102 |

La colonna *frozen KG* e' zero ovunque, e non e' un difetto della misura: lo
schema V2 non modella nessuna di queste dimensioni. E' esattamente il vuoto che
il corpus esiste per riempire.

`resection_status` resta a zero perche' nessuna fonte disponibile lo afferma. Non
viene inventato.

**Metriche del corpus:**

| Metrica | Valore |
| --- | --- |
| `source_profile_coverage` | 0.0588 |
| `statement_profile_coverage` | 1.0000 |
| `qualifier_addition_coverage` | 0.0819 |
| `qualifier_provenance_completeness` | **1.0000** |
| `ambiguous_qualification_rate` | 0.1569 |
| `conflict_rate` | 0.3000 |
| `unresolved_source_rate` | 0.0000 |

`statement_profile_coverage` vale 1.0 e va letto con attenzione: significa che
ogni statement ha **una unita' associata**, non che ogni statement sia
qualificato. Gli statement che ricevono almeno un qualificatore clinico sono
**9 su 147**.

**Metriche di linking:** tutte `not_evaluable`, perche' non esiste ancora un gold
annotato. La causa e' verificata e non supposta: tutte e 10 le prediction del
linker hanno un record di gold corrispondente, quindi lo zero viene dalle
annotazioni mancanti e non da un join rotto.

---

## 12. Freeze

`freeze_status` e' **calcolato dai fatti**, non impostabile su richiesta. Le
guardie bloccano il freeze se manca una seconda revisione richiesta, se esistono
disagreement non adjudicati, se gli hash non coincidono, se il corpus contiene
unita' con valori clinici e nessuna fonte dichiarata, se restano identificatori
non risolti o se la provenance e' incompleta.

Il manifest distingue `blocked` da `awaiting_second_review`: il primo descrive un
corpus con un difetto, il secondo un corpus sano ma non finito. Confonderli
farebbe sembrare rotto un lavoro semplicemente incompleto.

**Stato attuale:** `awaiting_second_review`, con un solo blocker — la seconda
revisione manca su tutte e 161 le coppie.

---

## 13. Limiti

1. **Sei unita' annotate su 102.** Tutto il resto e' infrastruttura.
2. **Nessuna metrica di linking e' calcolabile**, per assenza di gold.
3. `evidence_design` copre 54 unita' e viene dal registro, non dalla lettura
   della fonte: dice il disegno dichiarato, non i dettagli del protocollo.
4. La **presenza preclinica non e' asseribile** dai metadati disponibili. Lo
   strato «fonti precliniche» richiesto dal protocollo resta scoperto, ed e'
   dichiarato tale invece di essere approssimato.
5. Una fonte revisionata il cui insieme di statement mostra piu' interventi viene
   forzata a `single_cohort`, perche' la revisione umana ha asserito un profilo
   solo. E' difendibile ma va confermato caso per caso.
6. Il `conflict_rate` di 0.30 e' calcolato su 10 link soltanto: e' una frazione
   con un denominatore troppo piccolo per essere un tasso.

---

## 14. Readiness

Documentata a parte, per dimensione, in
[`QUALIFIED_RETRIEVAL_READINESS.md`](../benchmarks/mtb_evidence/v3/qualification_corpus/QUALIFIED_RETRIEVAL_READINESS.md).

Sintesi: **non pronto** per un retrieval qualificato sulle dimensioni cliniche;
**pronto** per malattia e intervento, che gli statement portano nativamente.

---

## 15. Decisioni cliniche ancora aperte

1. **Quali dimensioni sono bloccanti** per considerare valido un link. Oggi:
   malattia e intervento.
2. **Un conflitto blocca l'intero link o solo le dimensioni coinvolte.** Oggi solo
   quelle coinvolte.
3. **`Cholangiolocellular Carcinoma` e `cholangiocarcinoma`** sono la stessa
   entita' ai fini della qualificazione? Oggi no, e il conflitto resta aperto.
4. **Quando due coorti sono «non separabili»** con i dati disponibili. Oggi la
   regola e' automatica e conservativa; serve una soglia clinica.
5. **Se un profilo revisionato che copre piu' interventi** debba essere suddiviso
   a posteriori in piu' unita'.
6. **Quale sia la dimensione minima di corpus annotato** perche' il confronto
   V2 vs V3-A dica qualcosa sulla qualificazione e non solo sulla
   rappresentazione.
