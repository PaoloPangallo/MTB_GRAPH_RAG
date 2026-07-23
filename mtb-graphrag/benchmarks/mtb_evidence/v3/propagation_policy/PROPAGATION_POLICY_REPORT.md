# Politica di propagazione dei qualificatori — report

## 1. L'incoerenza trovata, e quanto era grande

La segnalazione riguardava due unità: quelle di PMID 22277784 propagabili dopo
una prima revisione non indipendente, quella di PMID 31358542 no.

Il conteggio dice altro. **103 unità su 158 risultavano propagabili**, e la
maggioranza non era mai stata guardata da nessuno:

| Stato | Propagabili prima |
|---|---:|
| `awaiting_source_review` (machine-extracted) | **80** |
| `human_reviewed` | 10 |
| `awaiting_first_review` | 9 |
| `first_review_complete` | 4 |

La causa è una sola riga di semantica. `is_propagatable` era definito come
`cohort_state in (single_cohort, resolved_cohort)`: rispondeva a **«la coorte è
identificata?»**, e veniva letto come se rispondesse a **«la revisione autorizza
a usare questo valore?»**. Finché le due domande hanno la stessa risposta
l'ambiguità non si vede. Smette di non vedersi appena una fonte a coorte unica
non è ancora stata revisionata — e in quel momento un valore estratto da una
macchina diventa indistinguibile da uno confermato da una persona.

C'era un secondo punto, più grave perché operativo: **il linker non consultava
affatto lo stato di revisione**. `build_link` applicava le dimensioni in base al
solo match sull'identificatore della fonte, e registrava `review_status` come
metadato senza che nulla ne dipendesse.

---

## 2. Revisione e propagazione sono due cose

Sono ora due proprietà distinte, e una terza le separa ulteriormente:

| Proprietà | Domanda a cui risponde |
|---|---|
| `cohort_is_resolved` | La coorte è identificata? (**necessaria**, non sufficiente) |
| `propagation_eligibility` | Che cosa autorizza la revisione? |
| `may_display_qualifiers` | Si può mostrare? |
| `is_propagatable` | Si può usare per **filtrare**? |

`is_propagatable` richiede ora entrambe le condizioni. La risoluzione della
coorte resta necessaria: nemmeno una adjudication rende propagabile un valore di
cui non si sa a quale braccio si applichi.

---

## 3. Prototipo e valutazione finale

La differenza fra `prototype_only` e `final` non è di grado.

Un qualificatore **mostrato** che sia sbagliato viene letto da qualcuno che può
accorgersene. Un qualificatore che **filtra** e sia sbagliato rimuove
un'evidenza, e nessuno vede ciò che non compare più. È lo stesso valore, con due
modi di sbagliare che non si assomigliano.

`prototype_only` consente: visualizzazione nella `QualifiedEvidenceView`, report
di audit, ispezione nel prototipo, esperimenti dichiarati provvisori.

`prototype_only` vieta: hard filtering, esclusione definitiva di evidenze,
metriche finali, gold, confronto V2 contro V3-A, dichiarazioni di applicabilità
clinica, dossier congelati.

---

## 4. La politica

```
machine_extracted / awaiting_source_review   → none
awaiting_first_review                        → none
source_checked_review_proposal               → none
first_review_complete (non indipendente)     → prototype_only
disagreement non adjudicato                  → prototype_only
second_review_complete + accordo esplicito   → final
adjudicated                                  → final
frozen                                       → final
```

Due casi sembrano promuovere e non promuovono, ed è deliberato:

- una **seconda revisione senza accordo esplicito** resta `prototype_only`: due
  revisioni non sono due accordi;
- una **coorte irrisolta** non diventa `final` nemmeno dopo adjudication.

I campi nativi degli EvidenceStatement non sono soggetti alla politica: vengono
dal grafo congelato, non da una revisione, e bloccarli renderebbe il sistema meno
capace senza renderlo più prudente.

---

## 5. Unità modificate

| | |
|---|---:|
| Unità esaminate | **158** |
| `none` | 142 |
| `prototype_only` | 16 |
| `final` | **0** |
| Normalizzate fisicamente | **4** |

Le quattro unità normalizzate sono quelle di PMID 22277784. Conservano tutto:
`first_review_complete`, il revisore, `resolved_cohort`, le decisioni, i locator,
i link, la provenienza, la parent superseded e la loro distinzione in una clinica
e tre precliniche. Cambia solo `propagation_eligibility`, che passa a
`prototype_only`, e con essa `is_propagatable`, `is_evaluable` e
`requires_second_independent_review`.

PMID 31358542 era già conforme: la fase precedente aveva scelto lo stato più
stretto, ed è quella scelta che questa fase generalizza.

Le altre 99 unità che dichiaravano `true` **non sono state riscritte**. Il loro
flag è un valore serializzato che il codice non onora più: caricando l'unità,
l'eligibility viene ricalcolata correttamente. Riscriverlo adesso invaliderebbe
`profile_units_hash` nel manifest del corpus e da lì lo snapshot fingerprint, che
è fuori perimetro. Sono contate a parte, come **flag serializzati obsoleti**, e
non come violazioni: sommarle farebbe sembrare la politica violata dove c'è solo
un dato non ancora riscritto.

---

## 6. Effetti sulla coverage

| | Prima | Dopo |
|---|---:|---:|
| Violazioni della politica | **103** | **0** |
| Qualificatori hard-filterable | — | **0** |
| Qualificatori prototype-visible | — | **142** |
| Flag serializzati obsoleti | — | 99 |

**Nessun dato è stato perso.** I 142 qualificatori restano tutti presenti, tutti
visibili nella vista, tutti ispezionabili. Cambia che cosa è lecito farne.

Che `hard_filterable_dimensions` sia vuota su ogni vista non è un difetto del
sistema: è lo stato reale della revisione, dove nessun qualificatore ha ancora
una seconda conferma indipendente. Prima quel numero sembrava alto perché contava
anche ciò che nessuno aveva confermato.

---

## 7. Readiness

```
single_global_policy              = true
review_and_propagation_distinct   = true
prototype_and_final_distinct      = true
hard_filtering_available          = false
gold_evaluable                    = false
ready_for_final_evaluation        = false
detector_promotion_ready          = false
```

---

## 8. Che cosa resta invariato

- le decisioni statement-level, di entrambe le fasi di revisione;
- il gold provvisorio, con le sue 12 annotazioni e `is_evaluable = false`;
- la provenienza, completa al 100% su ogni unità;
- i 70 packet della seconda revisione, byte per byte;
- la parent unit superseded di PMID 22277784, con i suoi quattro riferimenti;
- gli artefatti dell'audit strutturale e del batch clinico/preclinico.

---

## 9. Perché la prima revisione non viene invalidata

Perché è stata fatta, ed è servita. La revisione di PMID 22277784 ha scoperto che
quella fonte conteneva una coorte clinica e tre pannelli cellulari, e ha prodotto
quattro unità distinte dove ce n'era una sbagliata. Nulla di quel lavoro è meno
vero oggi.

Quello che cambia è cosa se ne può fare **senza una seconda conferma**. Una prima
revisione non indipendente è una fonte di informazione eccellente e un
riferimento pessimo: usarla per filtrare significherebbe misurare il sistema
contro il giudizio di una sola persona, che è la circolarità che il corpus esiste
per evitare.

Riportare le quattro unità a `source_checked` avrebbe cancellato il lavoro.
Lasciarle propagabili avrebbe cancellato la distinzione. `prototype_only` è
l'unico stato che tiene entrambe le cose.

---

## 10. Condizioni per la promozione

Una unità passa a `final` quando ricorre **una** di queste, e la coorte è
identificata:

1. una seconda revisione indipendente con accordo esplicito;
2. una adjudication su un disaccordo;
3. l'inserimento in un dossier congelato.

`is_evaluable` richiede in più che il gold copra quel collegamento: essere
propagabile e essere misurabile restano due cose diverse.

Il validatore è eseguibile e tipizzato: `UnreviewedPropagationError`,
`NonIndependentPropagationError`, `UnresolvedDisagreementError`,
`PrototypeHardFilterError`, `EvaluabilityError`.

---

## Prossimo passo

**L'approvazione di `SOURCE_REVIEW_PMID-22235099.md`**, la seconda fonte del
batch clinico/preclinico — quella con quattro sistemi preclinici di cui uno a
esito negativo. Nascerà direttamente `prototype_only`, senza bisogno di una
normalizzazione successiva.
