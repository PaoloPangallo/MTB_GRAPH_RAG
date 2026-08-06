# 08 — Minacce alla validità

## Validità di costrutto

**La fedeltà misurata è rispetto a un export, non al database originale.**
RQ1 confronta le candidate con l'export CSV congelato dichiarato in
`manifest.json` come `regenerable_from`. Se l'export stesso divergesse dal
Knowledge Graph da cui è stato prodotto, la divergenza sarebbe invisibile: la
misura risalirebbe fino all'export e non oltre. Neo4j non è attiva e non è
stata la sorgente della materializzazione, quindi non esiste un secondo
riferimento con cui triangolare.

**La contract fidelity non misura l'adeguatezza delle regole.**
`precision = recall = 1.0` significa che l'implementazione fa esattamente ciò
che le sei regole dichiarate prescrivono. I tre difetti di graph fidelity
mostrano che ciò non basta: le regole stesse perdono informazione. Chi legga solo
la prima cifra concluderebbe che la materializzazione è corretta.

**La riderivazione indipendente condivide due funzioni con l'originale.**
La derivazione di `edge_id` e di `payload_hash` è riprodotta invece che
riprogettata. Sono funzioni di identità documentate in `schema.json`, e un
qualunque errore di *contenuto* cambierebbe comunque il digest — ma un errore
*nella funzione di identità stessa* non sarebbe rilevabile.

**«Diagnosi falsa» è una definizione operativa.**
In RQ4 `non_actionable_false_diagnosis` conta le entità oncologiche non presenti
nel testo, usando un lessico minimo di 22 termini. Un'inferenza oncologica
espressa con termini fuori da quel lessico non verrebbe contata. La metrica è un
**limite inferiore**.

## Validità interna

**Due definizioni di misura sono state corrette dopo aver visto gli output.**
`non_actionable_false_diagnosis` e `adversarial_instruction_compliance` sono
passate da 4 e 1 a 0 dopo la correzione. È la minaccia più seria di questo
studio e va valutata direttamente:

* il **gold non è stato toccato**: `benchmark.jsonl` ha lo stesso
  `sha256 dd639ed0…` con cui è stato congelato e committato *prima* della prima
  chiamata, e un test lo verifica a ogni esecuzione;
* le correzioni allineano il codice a criteri **già scritti nel gold congelato**
  e nel protocollo: il §19 richiede l'assenza di *diagnosi oncologiche*, e la
  nota congelata del caso G1 dichiarava già che estrarre un farmaco letteralmente
  presente non è un'allucinazione;
* entrambi i fenomeni restano riportati, con il loro conteggio pieno, come
  `symptom_copied_into_disease_field = 5` e
  `injected_drug_extracted_as_target = 1`. Nessun dato è stato soppresso.

Resta il fatto che le definizioni sono state affinate osservando i risultati. Un
lettore che consideri la definizione iniziale più appropriata trova nel report i
numeri per entrambe.

**Un solo modello, una sola versione di prompt, 35 casi.**
Nessuna conclusione su altri modelli o su un prompt diverso è supportata.

**L'endpoint di default non funziona.**
Il runtime, come configurato, fallisce il 100 % delle chiamate. La valutazione ha
usato l'override previsto da `llm_config.base_url()`. RQ4 descrive quindi il
comportamento del parser su un endpoint funzionante, non della pipeline così
com'è oggi installata.

**Il benchmark è stato scritto dallo stesso agente che ha eseguito la
valutazione.** Il rischio di costruire casi che il sistema supera è reale. È
mitigato dal fatto che i 5 casi `IN_SCOPE_COMPLETE` provengono dal runtime e non
dall'agente, e dal fatto che il benchmark **ha** prodotto fallimenti (25.7 % di
non conformità, contraddizioni mai segnalate, ambiguità mancate). Non è mitigato
per le altre 6 categorie.

## Validità esterna

**Un solo Knowledge Graph, una sola versione.** 46 864 candidate da un export
CIViC/DGIdb/ClinicalTrials. Le quote di difetto (14.4 % di inversioni, 2.3 % di
alterazioni perse) sono proprietà di *questo* corpus.

**Il campione PMID è piccolo in termini di documenti.** 2 229 PMID unici, ma solo
15 documenti disponibili in cache: il livello C (documentary support) non è
valutabile su scala.

**RQ3 è vincolato a questo corpus.** La conclusione «0 candidate interrogabili»
dipende dal fatto che questa materializzazione non propaga alteration e disease
alle regole non-Evidence. Su una materializzazione corretta il risultato sarebbe
diverso.

## Validità di conclusione

**La pertinenza semantica dei PMID non è misurata.**
`semantic_pmid_precision_claimed_without_gold = false`. Le colonne del revisore
nei due campioni manuali sono vuote. Qualunque affermazione sulla pertinenza
richiede quell'annotazione.

**Nessun LLM è stato usato come giudice.** Né il modello sotto test né altri. Gli
indicatori automatici della pipeline (`support_status`, `coherence_status`,
quote/ABSTAIN) sono registrati come contesto e **non** entrano in alcuna metrica.
Il corpus `evidence_bundle` contiene 25 bundle prodotti dalla stessa pipeline in
valutazione: usarli come verità sarebbe autovalutazione.

**Nessuna affermazione di validità clinica.** Il livello D non è stato valutato.
In particolare, che le 486 candidate con inversione siano *dannose in uso reale*
non è dimostrato; è dimostrato che contraddicono il proprio record sorgente.

**Le metriche critiche a 0 vanno lette con il tasso di non conformità.**
`out_of_scope_false_oncology_extraction = 0` è un risultato reale, ma in 9 casi
su 35 il modello non ha prodotto alcun CaseContext: per quei casi la metrica è
vacuamente soddisfatta. Il risultato robusto è che nei 26 casi con tool call
valida **nessuna entità oncologica assente dal testo è stata prodotta**.

## Riepilogo

| Minaccia | Gravità | Mitigazione |
|---|---|---|
| Fedeltà misurata sull'export, non sul KG | Media | Dichiarata; nessuna alternativa disponibile |
| Contract fidelity scambiata per correttezza | **Alta** | Due layer riportati sempre separatamente |
| Definizioni di misura corrette post-hoc | **Alta** | Gold immutato e verificato; entrambi i conteggi riportati |
| Benchmark autoprodotto | Media | 5 casi dal runtime; fallimenti reali osservati |
| Modello e prompt singoli | Media | Dichiarata |
| Pertinenza semantica non misurata | Media | Dichiarata; campioni pronti per annotazione |
| Endpoint di default rotto | Bassa per RQ4, **alta per il prodotto** | Documentato come difetto a sé |
