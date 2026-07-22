# Risultati del pilota MTB-Evidence

**Studio pilota tecnico su quattro casi development.** Non è una validazione clinica.

- **Snapshot:** `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`, verificato
  prima di ogni run
- **Run:** 24 (4 casi × 2 architetture × 3 seed), 0 fallite
- **Modelli:** planner `gpt-oss:120b-cloud`, verifier `gpt-oss:20b-cloud`,
  report `gpt-oss:120b-cloud`
- **Ablation di reporting:** 4 bracci su retrieval congelato identico

---

## 1. Quanto clinical gold è presente nel KG

Copertura per caso, dallo snapshot gold:

| Caso | Terapie | PMID | NCT | Claim |
| --- | ---: | ---: | ---: | ---: |
| K1 FGFR2 | 0.75 | 0.50 | **0.00** | 0.00 |
| A2 ALK | 1.00 | 0.50 | **0.00** | 0.33 |
| C1 EGFR | 1.00 | 0.67 | 0.33 | 0.67 |
| N1 RMI2 | n/d | n/d | n/d | 1.00 |

Aggregato: 3 PMID esistono come nodo `Publication`, 3 solo dentro `Evidence.citation_id`,
2 sono assenti del tutto; **1 NCT su 6**; futibatinib esiste come nodo `Drug` ma nessun
percorso del caso vi arriva; i 24 qualificatori sono tutti assenti perché lo schema non
li modella.

## 2. Quanto snapshot gold viene recuperato

| Metrica | Valore |
| --- | ---: |
| `therapy_recall` | 0.667 |
| `therapy_precision` | **0.167** |
| `pmid_recall` | 0.333 |
| `required_tool_recall` | 1.000 |
| `unnecessary_tool_rate` | 0.250 |
| `negative_case_accuracy` (N1) | **1.000** |

Il recall è calcolato su ciò che era **realmente recuperabile**: gli elementi assenti dal
grafo non entrano nel denominatore.

Due casi meritano attenzione.

**K1 ha `therapy_recall` 0.000.** Il traversal recupera derazantinib e infigratinib — non
pemigatinib né futibatinib. L'audit aveva trovato pemigatinib raggiungibile, ma per un
percorso diverso da quello che la pipeline usa per i profili di fusione. È un disallineamento
fra il traversal e la struttura del grafo, non un errore del gold.

**C1 ha `therapy_precision` 0.111.** Recupera 9 terapie dove il gold ne attende una:
recall pieno, molto rumore.

## 3. Quanto retrieval sopravvive nel report

| Metrica | Valore |
| --- | ---: |
| `citation_accuracy` | **1.000** |
| `structural_coverage` | 0.906 |
| `qualifier_preservation` | 0.333 |
| `unsupported_claim_rate` | 0.139 |

Nessuna citazione inventata in 24 run. Il report conserva il 90,6% degli elementi
recuperati, ma il 13,9% delle sue claim non trova ancoraggio nei record — vale la pena
guardarlo insieme all'ablation (§8), dove il confronto è più pulito.

## 4. Quali qualificatori si conservano

`qualifier_preservation` 0.333 e `applicability_status_accuracy` **0.000**.

Il secondo numero è il più severo del documento e va letto con precisione: il sistema non
ha mai dichiarato un'applicabilità **coincidente con quella del gold**. Non significa che
abbia sbagliato attivamente — `compatible_overstatement_rate` è **0.000**, quindi non ha
mai presentato come applicabile una fonte che il gold marca non applicabile. Significa che
non emette affatto il giudizio nella forma che il gold richiede.

`human_review_routing_accuracy` 0.500: instrada correttamente alla revisione umana in metà
dei casi.

## 5. Dove avviene ogni perdita

Loss decomposition, 54 stati su 9 claim × 6 run. Partizione verificata: ogni claim riceve
esattamente uno stato.

| Stato | Conteggio | Stadio |
| --- | ---: | --- |
| `missing_from_kg` | 24 | knowledge graph |
| `misrepresented_in_report` | 12 | report |
| `partially_modelled_in_kg` | 6 | knowledge graph |
| `applicability_error` | 6 | qualificazione |
| `correctly_abstained` | 6 | — |

**Il 55% delle perdite avviene nel knowledge graph, prima che qualunque sistema entri in
gioco.** Nessuna architettura e nessun modello potrebbe recuperarle.

Per caso: A2 perde 12 claim nel KG e ne travisa 6; C1 perde 6 nel KG, ne travisa 6 e sbaglia
l'applicabilità di 6; K1 ha 6 claim parzialmente modellate e 6 assenti; N1 si astiene
correttamente in tutte e 6 le run.

## 6. Quale modello è stato selezionato e perché

| Ruolo | Modello | Motivo |
| --- | --- | --- |
| planner | `gpt-oss:120b-cloud` | punteggio 0.943, `required_tool_recall` 0.970 |
| verifier | `gpt-oss:20b-cloud` | punteggio 0.975, `qualifier_extraction` 0.938 |
| free report | `gpt-oss:120b-cloud` | unico ammissibile con `qualifier_preservation` alta |

Su 192 run di selezione. **Due avvertenze**, generate automaticamente nel report della
selezione perché i numeri da soli le nasconderebbero:

- Con 12 run per ruolo, un solo output non valido porta `valid_output_rate` a 0.917 e fa
  scattare l'esclusione a 0.95. `nemotron-3-ultra` è stato escluso dal free report per **un
  fallimento su dodici**, pur avendo `qualifier_preservation` 1.000 — la migliore del gruppo.
- `gpt-oss:120b` è l'unico modello con `citation_accuracy` sotto 1.000 (0.960) e l'unico con
  `unsupported_claim_rate` diverso da zero: è l'unico che ha inventato una citazione, ed è
  quello selezionato per scrivere i report.

## 7. Deterministico e agentico differiscono?

**Su ogni metrica di qualità: no.** `therapy_recall`, `precision`, `pmid_recall`,
`citation_accuracy`, `qualifier_preservation`, `structural_coverage`, `task_completion`,
`required_tool_recall` — identici fra le due architetture su tutti e quattro i casi.

Differiscono in tre cose:

| | deterministico | agentico |
| --- | ---: | ---: |
| `planner_calls` | **0** | **5** |
| latenza mediana | **2,1 s** | **10,1 s** |
| ordine degli strumenti | fisso | riordinato |

Il riordino è la parte interessante. Su **A2**, il caso di resistenza, il planner anticipa
`check_resistance` subito dopo `interpret_variant` — clinicamente l'ordine giusto, mentre il
piano fisso lo esegue per ultimo. Ma su **C1** l'ordine varia fra i seed: due esecuzioni
producono sequenze diverse.

Poiché entrambe le architetture eseguono comunque tutti e quattro gli strumenti, il riordino
non cambia ciò che viene recuperato. Su questi quattro casi l'adattamento del percorso costa
5 chiamate al planner e 5× di latenza senza produrre un risultato diverso.

**Questo non dimostra che il planner sia inutile.** Dimostra che su quattro casi noti, con un
piano fisso che copre già tutti gli strumenti necessari, non ha modo di distinguersi. Un caso
in cui il piano fisso invocasse lo strumento sbagliato, o in cui fermarsi presto contasse,
non è presente in questo campione.

## 8. Il report verificato supera la sintesi libera?

Ablation su retrieval congelato identico — `reporting_ablation_manifest.json` registra i
`record_ids` per caso come prova dell'input condiviso.

| Metrica | libero | raw | strutturato | verificato |
| --- | ---: | ---: | ---: | ---: |
| `citation_accuracy` | 1.000 | 1.000 | 1.000 | 1.000 |
| `qualifier_preservation` | 0.438 | 0.278 | 0.000 | **1.000** |
| `structural_coverage` | **0.325** | 1.000 | 1.000 | 1.000 |
| `unsupported_claim_rate` | 0.036 | 0.000 | 0.000 | 0.000 |

**Il vantaggio del braccio verificato sui qualificatori non è merito della scrittura.**
Setting, linea e popolazione non esistono nel grafo: vivono solo nei profili annotati a mano,
e quel braccio è l'unico che li consulta. Gli altri non li omettono per negligenza, non li
hanno.

Il confronto **pulito** è fra sintesi libera e strutturato non verificato: stesso input,
nessuno dei due consulta i profili. Lì la sintesi libera copre **0.325** di ciò che il
retrieval ha trovato contro 1.000, e produce claim non ancorate dove il deterministico è a
zero. Queste due differenze sono attribuibili al modo di scrivere, ed è questo il risultato
che sostiene la tesi sul reporting strutturato.

Nota sulla riproducibilità: il braccio libero è l'unico non deterministico. Due esecuzioni
consecutive **a temperatura 0** danno 0.365 e 0.325 di copertura.

## 9. Il caso RMI2 produce astensione?

**Sì, in tutte e 6 le run** (2 architetture × 3 seed). `negative_case_accuracy` 1.000,
`abstention_accuracy` 1.000, zero terapie, zero PMID, zero NCT emessi.

Il nodo `Gene` RMI2 esiste ma non ha alcuna relazione, e la prova negativa è archiviata in
`negative_path_proof.json` con query, risultato vuoto, fingerprint e timestamp.

**Un'avvertenza metodologica che vale più del risultato.** Durante lo sviluppo del runner,
una prima esecuzione ha prodotto `correctly_abstained` per N1 con Neo4j irraggiungibile:
tutti gli strumenti fallivano, la raccolta restava vuota, e l'astensione risultava corretta
**per il motivo sbagliato**. Il risultato qui sopra vale perché il runner verifica ora, prima
di ogni run live, che il grafo risponda e che il fingerprint coincida.

## 10. Quanto incidono modello, cache e latenza

- **Latenza per architettura:** deterministico 2,1 s mediani, agentico 10,1 s. Il costo è il
  planner: 5 chiamate contro 0.
- **Modello:** sul planner le latenze mediane vanno da 2,7 s (`gemma4:31b`) a 48,5 s
  (`nemotron-3-ultra`), un fattore 18 senza un guadagno di qualità corrispondente.
- **Cache:** isolata per modello, ruolo, architettura e condizione cold/warm; la chiave
  include source ID, hash dello statement, prompt version, model revision e schema version.
- **Hardware:** la macchina non ha GPU. Un modello locale da 14B impiega 117 s per il compito
  più piccolo del protocollo, contro 5 s sul cloud: è il motivo per cui l'intero esperimento
  gira su endpoint remoto.

## 11. Quali conclusioni non sono ammesse

Il campione è di **quattro casi**. Le conseguenze vanno dichiarate insieme ai numeri.

- I valori **descrivono questo campione**. Non stimano una popolazione di casi clinici.
- I tre seed sono **repliche della stessa unità**, non casi indipendenti. Non vanno contati
  come n=12.
- Nessun intervallo di confidenza: con questo n sarebbe più ampio dell'intervallo dei valori
  possibili. Nessun p-value viene riportato, e nessuno andrebbe usato come prova di efficacia.
- **Nessuna inferenza di superiorità generalizzabile.** L'assenza di differenza fra le due
  architetture è un risultato osservato su quattro casi, non una dimostrazione di equivalenza.
- I quattro casi sono stati usati per **selezionare il modello**: non costituiscono una
  valutazione indipendente di quel modello.
- La domanda di C1 nomina la terapia attesa (osimertinib), quindi il recall terapeutico di
  quel caso è meno informativo degli altri. `leakage_overlap` lo registra.
- Il confronto fra i modelli cloud è **esplorativo fra famiglie e scale differenti**: non
  permette di attribuire causalmente un miglioramento alla sola taglia.
- Il clinical gold è in **prima annotazione**: la seconda revisione indipendente è aperta, e
  i profili delle fonti sono `human_reviewed` ma non `frozen`.

## Terminologia

Questo è uno studio **tecnico** su un knowledge graph. Misura se un sistema conserva fatti,
fonti e qualificatori recuperati da un grafo. Non ha mai osservato un esito clinico, e
nessuna metrica qui calcolata potrebbe supportare un'affermazione su un paziente.

Si parla di *valutazione tecnica*, *ricostruzione dell'evidenza*, *supporto alla revisione*,
*studio pilota*, *risultato sul campione*, *applicabilità stimata*, *revisione umana
richiesta*. Mai di validazione clinica, terapia corretta, raccomandazione clinica corretta,
utilità oncologica dimostrata o sistema pronto all'uso clinico.

## Riproduzione

```bash
cd mtb-graphrag
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/build_snapshot_gold.py
PYTHONPATH=. python benchmarks/mtb_evidence/model_selection/scripts/run_model_selection.py \
    --models gpt-oss:20b-cloud gemma4:31b-cloud gpt-oss:120b-cloud nemotron-3-ultra-cloud \
    --roles planner verifier free_report --seeds 20240517 13 991 --resume \
    --output benchmarks/mtb_evidence/model_selection/results/v1
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/run_pilot_evaluation.py \
    --selected-models benchmarks/mtb_evidence/model_selection/results/v1/selected_models.json \
    --architectures deterministic agentic --seeds 20240517 13 991 --resume \
    --output benchmarks/mtb_evidence/evaluation/results/pilot_v1
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/run_reporting_ablation.py \
    --selected-models benchmarks/mtb_evidence/model_selection/results/v1/selected_models.json \
    --output benchmarks/mtb_evidence/evaluation/results/pilot_v1
```
