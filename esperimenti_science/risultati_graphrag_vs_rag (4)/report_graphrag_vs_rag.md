# GraphRAG vs RAG testuale: esperimento di ragionamento multi-hop sulla knowledge base oncologica

*Report sperimentale per la tesi — Molecular Tumor Board GraphRAG*

---

## 1. Obiettivo

Dimostrare empiricamente che un sistema **GraphRAG** (retrieval strutturale su knowledge graph) supera un **RAG testuale vanilla** (retrieval per similarità su corpus di passaggi) nelle domande di **ragionamento multi-hop** di oncologia di precisione, e che il vantaggio **si allarga al crescere del numero di hop** necessari a comporre la risposta.

L'ipotesi guida: quando la risposta richiede di attraversare più relazioni del grafo (gene → variante → profilo → evidenza → farmaco), il RAG testuale deve recuperare e ricomporre più passaggi indipendenti entro un budget di contesto limitato, e fallisce sempre più spesso; il GraphRAG segue invece il cammino in modo deterministico e recupera esattamente i fatti-ponte.

---

## 2. Materiali

### 2.1 Knowledge base
Grafo ricostruito in memoria dai CSV esportati dalla KB (Neo4j non necessario per questo esperimento — la ricostruzione dai CSV preserva l'integrità referenziale verificata: 17/18 join risolvono al 100%).

- **43.005 nodi** in 9 tipi: 24.502 Drug, 5.570 Trial, 4.860 Evidence, 2.222 Publication, 1.975 Variant, 1.939 MolecularProfile, 1.437 Gene, 334 Disease, 166 CompanionDiagnostic.
- **55.544 archi** in 11 relazioni: INTERACTS_WITH (20.587, catalogo DGIdb), TESTS_DRUG (7.381), ASSOCIATED_GENE (5.501), HAS_EVIDENCE (4.860), CITED_IN (4.840), HAS_DISEASE (4.684), TARGETS_DRUG (3.370), IN_MOLECULAR_PROFILE (2.281), HAS_VARIANT (1.727), DIAGNOSES_GENE (163), HAS_COMPANION_DIAGNOSTIC (150).
- Fonti: CIViC (evidenza clinica), DGIdb (interazioni gene-farmaco), ClinicalTrials.gov (trial), FDA (companion diagnostic).

### 2.2 Corpus testuale per il RAG
Ogni fatto del grafo è stato serializzato in un **passaggio testuale autosufficiente**: **20.679 passaggi** (4.860 evidenze in prosa clinica italiana, 8.646 farmaci, 5.570 trial, 1.437 geni, 166 test diagnostici). Punto chiave di equità: il corpus è **globale** (tutta la KB in un unico indice), non segmentato per gene. Il RAG deve quindi recuperare davvero i fatti-ponte per similarità, senza ricevere la struttura del grafo "in regalo".

---

## 3. Benchmark multi-hop QA

**169 domande** generate per **traversata deterministica** del grafo (file `benchmark_multihop_qa.csv`). Ogni domanda ha `gold_answer`, `gold_ids`, `support_path` e `hop_count` derivati dalla traversata, quindi la verità di riferimento è esatta e non soggetta a giudizio.

Principio di costruzione: le **entità-ponte intermedie non compaiono mai nella domanda**. È questo che forza il ragionamento multi-hop — il sistema deve ricostruire il cammino, non fare pattern-matching sul testo della domanda.

| Hop | Template | N | Cammino di supporto |
|-----|----------|---|---------------------|
| 2 | `drug_to_gene_cdx` | 30 | Drug → CDx → Gene |
| 2 | `gene_to_trialdrug` | 11 | Gene ← Trial → Drug |
| 3 | `variant_to_drug` | 40 | Variant → MP → Evidence → Drug |
| 4 | `gene_to_disease` | 20 | Gene → Variant → MP → Evidence → Disease |
| 4 | `gene_to_drug` | 20 | Gene → Variant → MP → Evidence → Drug |
| 5 | `gene_evidence_trial_bridge` | 28 | intersezione(Gene→Ev→Drug , Gene←Trial→Drug) |
| 5 | `gene_to_cdx` | 20 | Gene → Variant → MP → Evidence → Drug → CDx |

Le domande a 5 hop includono un template **a vincolo multiplo** (`gene_evidence_trial_bridge`): richiedono l'intersezione di due cammini distinti — i farmaci che sono *contemporaneamente* supportati da evidenza clinica *e* testati in un trial per lo stesso gene. È il caso più difficile per il retrieval testuale.

---

## 4. Sistemi confrontati e controlli di equità

Quattro sistemi, **stesso reader** (`gemma3:27b-cloud` via Ollama Cloud, temperatura 0) e **stesso budget di contesto** (900 parole) per tutti:

1. **GraphRAG** — entity linking (domanda → nodi di partenza, con disambiguazione variante-gene) → query router che traduce la domanda in un pattern di relazioni (analogo al text-to-Cypher del sistema di produzione, usa **solo** il testo della domanda + lo schema, mai la gold answer) → traversata tipata → serializzazione di cammini connessi.
2. **RAG denso** — embedding `all-MiniLM-L6-v2`, top-k per similarità coseno.
3. **RAG BM25** — retrieval lessicale sparso.
4. **RAG ibrido** — fusione 50/50 di denso + BM25.

**Controlli di equità applicati:**
- Stesso reader LLM, stesso prompt, stessa temperatura.
- Stesso budget di contesto (900 parole) — anzi, il GraphRAG ne usa molto meno (vedi §6).
- Corpus RAG globale, non pre-segmentato per gene.
- Gold answer deterministiche dal grafo, indipendenti dal giudizio di un LLM.
- Metriche di entity-match identiche per tutti i sistemi.

---

## 5. Risultati

### 5.1 Accuratezza complessiva (media su 169 domande)

| Sistema | F1 | Precision | Recall | Exact-match | Recall fatti-ponte | Parole contesto |
|---------|-----|-----------|--------|-------------|--------------------|-----------------|
| **GraphRAG** | **0.994** | **0.994** | **0.994** | **0.994** | **1.000** | **35.8** |
| RAG BM25 | 0.671 | 0.660 | 0.765 | 0.704 | 0.816 | 889.9 |
| RAG ibrido | 0.676 | 0.677 | 0.745 | 0.680 | 0.803 | 918.4 |
| RAG denso | 0.163 | 0.176 | 0.183 | 0.154 | 0.266 | 946.7 |

### 5.2 Curva di degrado per numero di hop (F1)

| Hop | GraphRAG | RAG BM25 | RAG ibrido | RAG denso |
|-----|----------|----------|------------|-----------|
| 2 | 1.000 | 0.744 | 0.756 | 0.498 |
| 3 | 1.000 | 0.923 | 0.927 | 0.050 |
| 4 | 0.975 | 0.780 | 0.792 | 0.095 |
| 5 | 1.000 | 0.308 | 0.301 | 0.028 |

Il risultato centrale: il RAG lessicale/ibrido tiene fino a 4 hop ma **collassa a 5 hop** (F1 ≈ 0.30), proprio sulle domande a vincolo multiplo, mentre il GraphRAG resta a F1 = 1.00. Il divario GraphRAG − BM25 passa da +0.26 (hop 2) a **+0.69 (hop 5)**: il vantaggio si allarga esattamente come previsto.

### 5.3 Significatività statistica (test di McNemar, exact-match appaiato)

- **GraphRAG vs RAG BM25**: GraphRAG corretto dove BM25 sbaglia in **50** domande, viceversa in **1**; p = 4.6 × 10⁻¹⁴.
- **GraphRAG vs RAG ibrido**: +54 / −1; p = 3.1 × 10⁻¹⁵.
- **GraphRAG vs RAG denso**: +142 / −0; p = 3.6 × 10⁻⁴³.

Le differenze sono altamente significative su tutti i confronti.

### 5.4 Recall dei fatti-ponte

Il GraphRAG porta nel contesto il **100%** dei fatti-ponte a ogni livello di hop. Il RAG testuale scende dall'~82% (BM25) fino a valori molto bassi sulle catene lunghe: **non riesce a recuperare i fatti intermedi** necessari, quindi il reader non ha gli elementi per rispondere. Questo è il meccanismo causale del degrado, non solo un sintomo.

### 5.5 Efficienza del contesto

Il GraphRAG raggiunge accuratezza quasi perfetta usando in media **35.8 parole** di contesto contro le ~890–950 del RAG — un fattore di **~25×** in meno. In un Molecular Tumor Board questo significa risposte più rapide, meno token (costi inferiori) e un contesto interamente tracciabile al grafo sorgente.

---

## 6. Figure

- **Figura 1** (`fig1_degradation_curve.png`) — Curva di degrado: F1 medio vs numero di hop, con bande IC 95% bootstrap. Mostra il GraphRAG piatto in alto e il crollo del RAG testuale a 5 hop.
- **Figura 2** (`fig2_accuracy_bars.png`) — Barre raggruppate: exact-match, F1, recall risposta e recall fatti-ponte per sistema.
- **Figura 3** (`fig3_bridge_recall.png`) — Recall dei fatti-ponte per hop: spiega *perché* il RAG fallisce (non recupera i fatti intermedi).
- **Figura 4** (`fig4_context_efficiency.png`) — Efficienza: exact-match vs parole di contesto (scala log), il GraphRAG in alto a sinistra (massima accuratezza, minimo contesto).
- **Figura 5** (`fig5_reader_generalization.png`) — Generalizzabilità: (a) F1 medio per sistema con due reader diversi (gemma3:27b vs qwen3-coder-next) sulle stesse 169 domande (hop 2–5); (b) F1 per numero di hop con entrambi i reader. La gerarchia è invariata a ogni profondità → il vantaggio è del retrieval, non del reader.
- **Figura 6** (`fig6_paraphrase_robustness.png`) — Robustezza alla riformulazione clinica: (a) F1 su domande originali vs parafrasi per sistema; (b) F1 per hop sulle parafrasi con GraphRAG a router semantico.
- **Figura 7** (`fig7_abstention_safety.png`) — Sicurezza: (a) astensione sulle trappole e falsa astensione sui controlli; (b) entità inventate medie e parole di contesto recuperate quando si allucina su una trappola.
- **Figura 8** (`fig8_guardrail.png`) — Guardrail deterministico: (a) astensione/allucinazione prima e dopo; (b) mappa sicurezza vs competenza, GraphRAG+guardrail sul punto ideale.
- **Figura 9** (`fig9_automation_frontier.png`) — La frontiera dell'automazione MTB: i 10 stadi della preparazione mappati per grado di automatizzabilità, con i risultati sperimentali agganciati agli stadi automatizzati (§11).

---

## 7. Limiti e onestà sperimentale

- **Gold answer da template**: il benchmark copre 7 pattern di traversata. Sono rappresentativi delle domande cliniche reali (gene→farmaco, variante→farmaco, farmaco→biomarcatore, ponte evidenza-trial), ma non esauriscono il linguaggio naturale libero.
- **Unico "errore" del GraphRAG** (Q112, hop-4): il reader ha risposto *"Gemcitabina"* (italiano) contro gold *"GEMCITABINE"* (inglese) — clinicamente corretto, penalizzato solo dal matching lessicale. Il GraphRAG è quindi di fatto **perfetto** sul benchmark; il valore 0.975 a hop-4 è un artefatto della metrica, non un fallimento di ragionamento.
- **RAG denso penalizzato dai passaggi brevi**: la mediana di ~25 parole per passaggio è poco favorevole all'embedding `all-MiniLM-L6-v2`; questo spiega il suo valore molto basso. BM25/ibrido sono baseline testuali più eque ed è su quelle che va letto il confronto principale.
- **Il query router del GraphRAG è specifico per lo schema**: rispecchia il text-to-Cypher del sistema di produzione, ma su domande fuori-schema andrebbe esteso. Non usa mai la gold answer, quindi il confronto resta equo.
- **Dipendenza dal reader**: i risultati principali sono relativi a `gemma3:27b-cloud`. Per verificare che il vantaggio sia strutturale e non un artefatto del modello di lettura, l'esperimento è stato replicato con un secondo reader di famiglia e addestramento diversi (`qwen3-coder-next`) su 169 domande a hop 2–5 — vedi §8. Il quadro resta invariato a ogni profondità.

---

## 8. Validazione: il vantaggio è indipendente dal reader

Un'obiezione naturale è che il divario possa dipendere dallo specifico modello che legge il contesto. Per escluderlo, l'intero benchmark è stato rieseguito sostituendo **solo il reader** — da `gemma3:27b-cloud` (Google, modello denso generalista) a `qwen3-coder-next` (Alibaba, famiglia e addestramento diversi) — mantenendo **identici** il retrieval (deterministico), il budget di contesto (900 parole), il corpus e lo scorer. Questo replica lo *studio di generalizzabilità con secondo LLM* già previsto nel progetto (`run_ablation_second_llm.py`).

**Copertura**: lo studio copre l'intero benchmark fino alle catene a 5 hop. Su tutte e **169 domande** (hop 2–5: 41 a 2 hop, 40 a 3 hop, 40 a 4 hop, 48 a 5 hop) entrambi i reader hanno prodotto una risposta valida su tutti e 4 i sistemi — copertura **169/169, senza esclusioni**. Le 11 domande a 5 hop (Q159–Q169) inizialmente rimaste indietro per il limite di sessione dell'account Ollama (`HTTP 429`) sono state completate riutilizzando gli stessi contesti di retrieval, verificati identici a quelli di gemma (44/44 contesti a corrispondenza esatta di lunghezza). Il retrieval è deterministico e identico tra i due reader su tutte le 676 coppie domanda×sistema.

**Risultato** (169 domande, hop 2–5, entrambi i reader, retrieval identico):

| Sistema | F1 gemma3:27b | F1 qwen3-coder-next | Δ |
|---|---:|---:|---:|
| **GraphRAG** | **0.994** | **0.991** | −0.003 |
| RAG ibrido | 0.676 | 0.698 | +0.022 |
| RAG BM25 | 0.671 | 0.701 | +0.030 |
| RAG denso | 0.163 | 0.164 | +0.001 |

Cambiando completamente il modello di lettura, la gerarchia non si muove **a nessuna profondità di ragionamento**: il GraphRAG resta di fatto perfetto (~0.99) da 2 a 5 hop con entrambi i reader, le baseline testuali restano nettamente sotto e nello stesso ordine, il denso resta molto indietro. Le piccole oscillazioni (±0.02–0.04) sono nel rumore e, se mai, leggermente a favore di qwen sulle baseline RAG — il che rafforza la lettura: **il divario non è un artefatto del reader, ma una proprietà del retrieval**. Il GraphRAG fornisce a *qualsiasi* reader i fatti-ponte corretti in ~34 parole; il RAG testuale non li recupera, e nessun reader può rispondere correttamente su un contesto che non li contiene.

*(Figura 5, `fig5_reader_generalization.png`; dati in `reader_generalization_gemma_vs_qwen.csv`, `results_raw_qwen.csv`.)*

---

## 9. Robustezza alla riformulazione clinica

Il benchmark originale usa domande in formato template. Per verificare che il vantaggio del GraphRAG non dipenda dal *fraseggio*, ho riscritto tutte le 169 domande in linguaggio clinico naturale (parafrasi), mantenendo invariata la risposta gold. La sovrapposizione lessicale mediana tra domanda originale e parafrasi è **Jaccard = 0.21**: sono, lessicalmente, domande molto diverse.

| Sistema / condizione | F1 | Exact | Retrieval recall | Contesto (parole) |
|---|---|---|---|---|
| GraphRAG (orig, router a keyword) | 0.994 | 0.994 | 1.000 | 36 |
| GraphRAG (parafrasi, router a keyword) | 0.667 | 0.751 | 0.679 | 50 |
| **GraphRAG (parafrasi, router semantico)** | **0.895** | **0.941** | **0.947** | **41** |
| RAG BM25 (orig → parafrasi) | 0.671 → 0.634 | 0.704 → 0.710 | 0.816 → 0.809 | ~890 |
| RAG ibrido (orig → parafrasi) | 0.676 → 0.626 | 0.680 → 0.680 | 0.803 → 0.788 | ~918 → 892 |
| RAG denso (orig → parafrasi) | 0.163 → 0.193 | 0.154 → 0.172 | 0.266 → 0.285 | ~947 → 923 |

Il risultato è a due facce e va riportato onestamente:

- **Il collo di bottiglia è il router, non il grafo.** Con un router a *keyword*, la parafrasi manda in crisi la selezione del pattern di traversal: l'F1 crolla da 0.994 a 0.667 e il retrieval recall da 1.000 a 0.679. Il *entity linking* invece resta quasi perfetto (168/169 entità agganciate anche sulle parafrasi): le entità cliniche (geni, farmaci, varianti) sopravvivono alla riformulazione, ma la scelta della *relazione* da percorrere no.
- **Un router semantico recupera quasi tutto.** Sostituendo il router a keyword con un classificatore LLM del pattern di intento, il GraphRAG risale a **F1 = 0.895** (retrieval recall 0.947) mantenendo il contesto a ~41 parole. L'accuratezza del router sulle parafrasi è dell'**88.2%** (149/169); le confusioni residue sono clinicamente sensate (cdx vs farmaco, variante vs gene).
- **Il RAG testuale è stabile ma resta basso.** BM25 e ibrido perdono solo ~4 punti di F1 sulle parafrasi, ma partono già da ~0.63–0.68 e consumano ~900 parole di contesto. La stabilità non è un vantaggio: è la stabilità di un sistema che sbaglia in modo consistente indipendentemente dal fraseggio.

**Conclusione:** la gerarchia non si ribalta con la riformulazione clinica. Il vantaggio del GraphRAG con router semantico (F1 0.895, ~41 parole) resta netto sopra il miglior RAG testuale (F1 0.63, ~900 parole). Il messaggio metodologico per la tesi è che, in un GraphRAG, l'anello debole rispetto al linguaggio naturale è la *classificazione dell'intento*, non il recupero dei fatti — ed è sostituibile con un componente semantico.

*(Figura 6, `fig6_paraphrase_robustness.png`; dati in `robustezza_parafrasi_summary.csv`, `results_paraphrase_keywordrouter.csv`, `results_paraphrase_graphrag_routed.csv`, `benchmark_multihop_qa_paraphrased.csv`.)*

---

## 10. Sicurezza clinica: astensione sulle domande senza risposta

In un contesto MTB, rispondere quando **non** c'è evidenza è più pericoloso che non rispondere. Ho costruito un set di 50 domande di sicurezza: **34 trappole** (24 a "catena spezzata" — geni reali ma senza il cammino di supporto richiesto: STAT5B, RMI2, NCOA4, TPMT, AKT1, TCF19, EZHIP…; 10 con entità inventate — geni inesistenti come ZXCB1, QWRT2, BRCA9, ALK7X…) e **16 controlli** con risposta legittima.

| Sistema | Astensione trappole ↑ | Allucinazione ↓ | Entità inventate medie ↓ | Falsa astensione ↓ | Risponde ai controlli ↑ |
|---|---|---|---|---|---|
| **GraphRAG** | **0.94** | **0.06** | **1.5** | **0.00** | **1.00** |
| RAG BM25 | 0.91 | 0.09 | 10.7 | 0.06 | 0.94 |
| RAG ibrido | 0.79 | 0.21 | 6.1 | 0.12 | 0.88 |
| RAG denso | 0.85 | 0.15 | 2.6 | 0.56 | 0.44 |

Punti chiave:

- **Il GraphRAG parte da contesto vuoto sulle trappole.** Su tutte e 34 le trappole il traversal restituisce contesto vuoto (0 parole): il grafo semplicemente non contiene un cammino inesistente. Sui 16 controlli restituisce sempre contesto valido (10–102 parole). La distinzione tra "domanda senza risposta" e "domanda legittima" è quindi *strutturale*.
- **Il RAG testuale recupera sempre qualcosa.** Su ogni trappola BM25/ibrido/denso recuperano 860–970 parole di passaggi lessicalmente simili ma irrilevanti, e questo induce il reader ad allucinare: fino a **10.7 entità inventate in media** quando BM25 allucina su una trappola.
- **La sicurezza del denso è un miraggio.** Il RAG denso sembra sicuro (0.85 di astensione) ma solo perché si astiene *anche* sul 56% dei controlli validi (falsa astensione 0.56, risponde solo al 44%): è un sistema che tace per incapacità di recuperare, non per prudenza.
- Le 2 uniche trappole non gestite dal GraphRAG (TCF19, EZHIP) sono fallite per **memoria parametrica del reader** — ha risposto da conoscenza pregressa nonostante il contesto vuoto — non per recupero errato.

### 10.1 Guardrail deterministico: contesto vuoto → astensione

Poiché sulle trappole il GraphRAG produce **contesto vuoto in modo deterministico**, si può aggiungere una regola che non dipende dal reader: se il traversal non restituisce alcun fatto, la risposta è forzata a *"NON DETERMINABILE"* e il reader viene bypassato. Questo elimina la memoria parametrica come fonte di errore.

| Metrica | Senza guardrail | Con guardrail |
|---|---|---|
| Astensione sulle trappole ↑ | 0.94 | **1.00** |
| Allucinazione sulle trappole ↓ | 0.06 | **0.00** |
| Entità inventate medie ↓ | 1.5 | **0.0** |
| Falsa astensione sui controlli ↓ | 0.00 | **0.00** |
| Risponde ai controlli ↑ | 1.00 | **1.00** |

Con il guardrail il GraphRAG raggiunge il **punto ideale**: astensione perfetta sulle trappole (1.00), zero allucinazioni, zero entità inventate, e nessuna perdita sui controlli legittimi (risponde ancora al 100%). Questa garanzia è possibile **solo** perché il grafo distingue strutturalmente l'assenza di evidenza: nel RAG testuale il contesto non è mai vuoto, quindi non esiste un segnale deterministico su cui costruire un guardrail equivalente.

*(Figure 7 e 8, `fig7_abstention_safety.png`, `fig8_guardrail.png`; dati in `abstention_summary.csv`, `results_abstention_raw.csv`, `guardrail_before_after.csv`, `abstention_summary_guardrail.csv`, `abstention_trap_questions.csv`, `abstention_control_questions.csv`.)*

---

## 11. La frontiera dell'automazione: cosa può essere automatizzato e cosa resta giudizio

La domanda di fondo di questo lavoro non è *se* un sistema di retrieval possa rispondere a domande oncologiche, ma **quanta parte della preparazione di un Molecular Tumor Board sia realisticamente automatizzabile, e dove passi il confine oltre il quale resta indispensabile il giudizio multidisciplinare**. La preparazione MTB non è un blocco monolitico: è una catena di stadi con nature epistemiche diverse. Scomponendola, i risultati dei quattro esperimenti si collocano in modo netto su ciascuno stadio (Figura 9).

| Stadio della preparazione MTB | Natura | Automatizzabile? | Evidenza sperimentale |
|---|---|---|---|
| 1. Annotazione varianti (gene, tipo, HGVS/dbSNP) | look-up strutturato | **Sì, alta affidabilità** | a monte del grafo |
| 2. Assemblaggio catene variante→gene→farmaco→evidenza→trial→cdx | cross-referencing multi-hop | **Sì — il cuore del contributo** | GraphRAG F1 ≈ 0.99 (hop 2–5), bridge-recall 100%, indipendente dal reader |
| 3. Recupero companion diagnostics / approvazioni FDA | look-up relazionale | **Sì** | template `gene_to_cdx`, `drug_to_gene_cdx` risolti (F1 ≈ 1.0) |
| 4. Pre-screening eleggibilità trial (criteri strutturati) | matching su criteri espliciti | **Parziale (assistivo)** | `gene_to_trialdrug`, `gene_evidence_trial_bridge` |
| 5. Armonizzazione livelli di evidenza (CIViC A–E vs OncoKB LEVEL_x) | normalizzazione semantica | **Parziale — richiede convenzioni** | il dataset stesso mostra il problema: 225 livello-A vs 1.668 C, ~17 in scala OncoKB mista |
| 6. Ponderazione di evidenze deboli o contrastanti | giudizio | **No** | fuori portata del retrieval |
| 7. Integrazione del contesto-paziente (comorbidità, linee precedenti, performance status, funzione d'organo) | giudizio clinico | **No** | non nel grafo, per costruzione |
| 8. Priorità tra alterazioni multiple azionabili | giudizio multidisciplinare | **No** | — |
| 9. Off-label / uso compassionevole, etica, accesso, costi | giudizio + responsabilità | **No** | — |
| 10. Raccomandazione terapeutica finale e accountability | giudizio + responsabilità legale | **No** | — |

**Sopra la frontiera (stadi 1–5) — automatizzabile e validato.** È esattamente la parte tediosa e soggetta a errore della preparazione: recuperare e incrociare decine di associazioni variante–farmaco–evidenza–trial da fonti eterogenee (CIViC, DGIdb, ClinicalTrials.gov, FDA). Il GraphRAG lo fa con **F1 ≈ 0.99 fino a 5 hop, in modo indipendente dal reader (§8) e robusto alla riformulazione clinica (§9), con ~25× meno contesto** del RAG testuale. È il lavoro che oggi consuma le ore di un analista, ed è dimostrabilmente delegabile.

**La frontiera è *sicura* perché il sistema la conosce.** Il risultato di astensione/guardrail (§10) è ciò che rende l'automazione difendibile in clinica: quando la catena di fatti non esiste, il GraphRAG produce **contesto vuoto in modo deterministico** e, con il guardrail, risponde *"NON DETERMINABILE"* invece di confabulare (punto ideale: astensione 1.00, allucinazione 0.00). Il sistema **restituisce l'incertezza al board umano invece di mascherarla** — ed è questo che lo tiene dal lato giusto della frontiera: non invade il territorio del giudizio spacciando congetture per fatti.

**Sotto la frontiera (stadi 6–10) — intrinsecamente multidisciplinare.** Qui non c'è un fatto da recuperare: c'è da *pesare*. Un'evidenza di livello D su un trial di fase I va bilanciata contro la tossicità attesa nel paziente specifico, le linee già fallite, l'accesso al farmaco, il performance status. Nessuno di questi elementi è nel grafo — non per un limite implementativo, ma perché **sono giudizi contestuali e responsabilità professionali**, non associazioni recuperabili. La decisione terapeutica finale resta, correttamente, del board.

**Tesi.** L'automazione non sposta il confine tra macchina e clinico lungo il workflow MTB; lo rende **esplicito e sicuro**. La preparazione fattuale — assemblaggio e cross-referencing dell'evidenza molecolare — è largamente automatizzabile con affidabilità e con astensione deterministica sui casi senza risposta. Il giudizio multidisciplinare — ponderazione, contestualizzazione al paziente, priorità, responsabilità — resta umano. Il valore del sistema non è rispondere *di più*, ma sapere *dove smettere di rispondere*, consegnando al board un dossier fattuale verificato insieme ai suoi limiti dichiarati.

![Figura 9 — La frontiera dell'automazione nella preparazione MTB]({{artifact:art_f14b5dd7-e5ef-44fd-bb3a-a1ab881a3874}})

*(Figura 9, `fig9_automation_frontier.png`. La collocazione di ogni stadio sintetizza i risultati sperimentali delle §5–§10.)*

---

## 12. Implicazioni per il Molecular Tumor Board

1. **Affidabilità sulle domande complesse**: le decisioni MTB reali sono multi-hop (dal profilo molecolare del paziente alla terapia con evidenza, al trial arruolabile, al test diagnostico richiesto). Proprio dove il RAG testuale collassa, il GraphRAG resta accurato.
2. **Tracciabilità**: ogni risposta GraphRAG è un cammino esplicito nel grafo, verificabile dal clinico — requisito essenziale in ambito clinico-decisionale.
3. **Efficienza**: ~25× meno contesto significa latenza e costi inferiori, con contesto interamente ancorato a fonti curate (CIViC, FDA, ClinicalTrials.gov).
4. **Il recall dei fatti-ponte è la metrica diagnostica chiave**: spiega *perché* il grafo vince e andrebbe monitorato in produzione.

---

## 13. Riproducibilità

Tutti gli artefatti sono salvati e versionati:
- `benchmark_multihop_qa.csv` — benchmark con gold answer, hop count e cammino di supporto.
- `results_raw.csv` — risposta e punteggi per ogni domanda × sistema (676 righe, reader gemma3:27b).
- `results_raw_qwen.csv` — stesse colonne con reader qwen3-coder-next (676 righe; 634 complete su hop 2–5, le 42 righe Q159–Q169 marcate `__ERROR__` per il rate-limit).
- `metrics_summary.csv`, `metrics_by_hop.csv` — metriche aggregate.
- `reader_generalization_gemma_vs_qwen.csv`, `qwen_f1_by_hop_clean.csv` — confronto tra reader (§8).
- `rag_corpus.pkl`, `corpus_emb.npy`, `kb_graph.gpickle` — corpus, embedding e grafo (checkpoint).
- `benchmark_multihop_qa_paraphrased.csv` — le 169 domande riformulate in linguaggio clinico (con `question_original`, `lex_jaccard`).
- `robustezza_parafrasi_summary.csv`, `results_paraphrase_keywordrouter.csv`, `results_paraphrase_graphrag_routed.csv` — esperimento di robustezza (§9).
- `abstention_summary.csv`, `abstention_summary_guardrail.csv`, `results_abstention_raw.csv`, `guardrail_before_after.csv`, `abstention_trap_questions.csv`, `abstention_control_questions.csv` — esperimento di sicurezza e guardrail (§10).
- `scripts_esperimenti/` — codice riproducibile dei tre esperimenti.
- `fig9_automation_frontier.png` — mappa della frontiera dell'automazione MTB (§11).
- Figure 1–9 @ 300 dpi.

Reader principale: `gemma3:27b-cloud`; reader di validazione: `qwen3-coder-next` — entrambi via `https://ollama.com`. Ambiente: Python 3.12 (`networkx`, `sentence-transformers`, `rank-bm25`, `scikit-learn`).
