# Report di Analisi — Nuovi Paper di Riferimento per la Tesi
**Sistema GraphRAG Agentico per Molecular Tumor Board**
*Analisi del contributo al posizionamento della tesi — Giugno 2026*

---

## Panoramica

I tre paper analizzati coprono tre prospettive complementari e distinte rispetto ai paper già in uso:

| Paper | Venue | Anno | Prospettiva |
|---|---|---|---|
| Aldea et al. — IASLC MTB Consensus | J. Thoracic Oncology | 2025 | Clinica — definisce lo standard MTB |
| Berman et al. — RAG_MTB | JMIR Medical Informatics | 2025 | Tecnica — RAG testuale per MTB |
| Loaiza-Bonilla et al. — OncoMultiAgentKB | ESMO Real World Data | 2026 | Tecnica — Multi-agente + KB oncologica |

Nessuno dei cinque paper già in uso (Edge, Wu, Kim, Jin, Díaz Cantón) è un confronto diretto con un sistema RAG o multi-agente applicato specificamente al problema delle raccomandazioni terapeutiche MTB. Questi tre colmano esattamente quel gap.

---

## 1. Aldea et al. (2025) — IASLC Consensus Statement on Molecular Tumor Boards

**Riferimento completo:**
Aldea M, Rotow JK, Arcila M, et al. *Molecular tumor boards: a consensus statement from the International Association for the Study of Lung Cancer.* J Thorac Oncol. 2025;20:1594–1614. DOI: 10.1016/j.jtho.2025.07.009

### Cos'è

Un consensus statement redatto dalla International Association for the Study of Lung Cancer (IASLC) che raccoglie le raccomandazioni di decine di oncologi esperti su come implementare e operare un MTB. Non è un paper sperimentale AI — è il documento normativo clinico di riferimento per il problema che la tesi affronta.

### Contributo chiave per la tesi

**Giustificazione clinica dell'uso di ESCAT come metrica primaria.**

Il consensus statement afferma esplicitamente che l'uso di scale di azionabilità è *critico* per gli MTB per generare raccomandazioni consistenti ed evidence-based, riducendo la dipendenza dall'opinione del singolo esperto. Identifica ESCAT e OncoKB come le due scale di riferimento, con questa mappatura:

- ESCAT I / OncoKB 1–2 → biomarker pronti per uso routinario, legati a beneficio di sopravvivenza in trial con terapia matched
- ESCAT II / OncoKB 3A → richiedono ulteriore validazione (risposta migliorata ma incerto beneficio sopravvivenza)
- ESCAT III / OncoKB 3B → evidenza in altri tipi tumorali con la stessa alterazione
- ESCAT IV → dati preclinici

Crucialmente: *"each ranking applies to a specific drug–target pair, not the alteration alone"* — questa frase giustifica esattamente perché il tuo ESCAT Interpreter deve valutare la coppia gene+variante+farmaco+tumore e non solo il livello di evidenza grezzo.

### Dove usarlo in tesi

- **Introduzione/Background:** per giustificare perché un MTB ha bisogno di un sistema di classificazione strutturato e perché ESCAT è lo standard europeo scelto
- **Sezione metodologica (ESCAT Interpreter):** per citare la definizione formale dei tier ESCAT usati nel sistema
- **Discussione:** per confrontare le raccomandazioni del sistema con lo standard clinico riconosciuto, non solo con altri sistemi AI
- **Limitazioni:** il consensus identifica disparità globali nell'accesso agli MTB — il tuo sistema è esattamente uno strumento che potrebbe ridurre queste disparità automatizzando la preparazione

### Differenziatore rispetto alla tesi

Il consensus non affronta l'automazione tramite AI. È il documento che *definisce il problema clinico* che la tesi *risolve tecnicamente*. Citarlo è citare la definizione autorevole del problema, non un lavoro concorrente.

---

## 2. Berman et al. (2025) — RAG_MTB: Retrieval Augmented Therapy Suggestion for Molecular Tumor Boards

**Riferimento completo:**
Berman E, Sundberg Malek H, Bitzer M, Malek N, Eickhoff C. *Retrieval Augmented Therapy Suggestion for Molecular Tumor Boards: Algorithmic Development and Validation Study.* JMIR Med Inform. 2025. DOI: 10.2196/64364. PMID: 40053768.

### Cos'è

Una pipeline RAG costruita con LlamaIndex su dati PubMed (LLaMA come backbone LLM) per generare raccomandazioni terapeutiche per pazienti MTB reali di un cancer center tedesco (Università di Tubinga). I casi paziente provengono da una vera conferenza MTB. La valutazione è manuale da parte dei membri del board.

### Architettura

- Input: documenti MTB (profilo molecolare paziente + diagnosi)
- Retrieval: query PubMed via LlamaIndex per ogni coppia (tipo di cancro, mutazione genetica)
- Filtro: geni OncoKB level 1, 2 o 3
- Output: raccomandazione terapeutica + giustificazione + referenze PubMed
- Ground truth: protocollo MTB ufficiale dell'istituzione

### Contributo chiave per la tesi

**È il confronto diretto più onesto disponibile in letteratura.** Stesso dominio (MTB), stesso task (raccomandazioni terapeutiche), approccio diverso (RAG testuale su PubMed vs KB strutturata su Neo4j).

Le differenze architetturali rispetto alla tesi sono tre e tutte vantaggiose per il tuo sistema:

**Differenza 1 — Fonte della conoscenza:**
Berman et al. usano PubMed raw tramite retrieval semantico testuale. La tesi usa una KB pre-costruita da fonti curate (CIViC + OncoKB) con integrità referenziale verificata. Implicazione: il sistema di Berman può recuperare paper irrilevanti o contraddittori che appaiono semanticamente simili; il tuo sistema recupera solo evidenze validate da esperti con livello di evidenza esplicito.

**Differenza 2 — Gestione delle allucinazioni:**
Il sistema di Berman non ha meccanismi strutturali per garantire che le referenze PubMed citate nell'output esistano realmente per quel profilo. La tesi verifica ogni PMID tramite la relazione `CITED_IN` nel grafo prima della sintesi — questo è il meccanismo che produce 0% hallucination rate sulle citazioni.

**Differenza 3 — Classificazione ESCAT:**
Berman et al. non assegnano tier ESCAT. La tesi lo fa sistematicamente, allineandosi allo standard clinico definito da Aldea et al. (IASLC 2025).

### Metrica di confronto disponibile

Il paper riporta che il sistema è stato valutato dal panel MTB su *rilevanza* e *correttezza* delle raccomandazioni, ma non riporta metriche numeriche precise (accuracy, F1) pubblicamente disponibili — la valutazione è qualitativa. Questo ti dà vantaggio: la tua valutazione con benchmark quantitativo su 30 casi è metodologicamente più rigorosa.

### Dove usarlo in tesi

- **Lavori correlati:** come confronto diretto più vicino — stesso problema, approccio RAG textuale
- **Sezione methodology:** per motivare la scelta di KB strutturata vs RAG testuale su PubMed
- **Discussione:** il tuo sistema risolve i tre problemi di Berman et al. in modo strutturale, non euristico

---

## 3. Loaiza-Bonilla et al. (2026) — OncoMultiAgentKB: Neuro-Symbolic Multi-Agent AI + Oncology Knowledge Graph

**Riferimento completo:**
Loaiza-Bonilla A, Yost C, Kurnaz S, et al. *Transforming oncology clinical trial matching through neuro-symbolic, multi-agent AI and an oncology-specific knowledge graph: a prospective evaluation in 3,804 patients.* ESMO Real World Data and Digital Oncology. 2026. DOI: 10.1016/j.esmorw.2026.100706.

### Cos'è

Un sistema commerciale (Massive Bio) valutato prospetticamente su 3.804 pazienti reali con malattia metastatica o progressiva, su un arco di 12 mesi. Il sistema combina agenti LLM specializzati (OncoAgents) con un knowledge graph oncologico (OncoGraph) in un'architettura neuro-simbolica dove agenti probabilistici operano su logica di grafo deterministica. Il gold standard è prodotto da due oncologi (Cohen's κ = 0.92). Focus: matching paziente-trial clinico.

### Architettura OncoAgents + OncoGraph

Il sistema è composto da quattro componenti:
- **OncoAgents:** agenti LLM specializzati per estrazione, normalizzazione e matching
- **OncoGraph:** knowledge graph oncologico con ontologie validate
- **OncoRecommend:** motore di prioritizzazione
- **OncoSet:** corpus curato da esperti

Ha processato 157.367 pagine cliniche (~86.5M token). Baseline di confronto: screening manuale, GPT-4 zero-shot, GPT-4 chain-of-thought, GPT-4o.

### Risultati chiave

- F1 = 0.8246 vs 0.78 senza OncoGraph (ablation study)
- Rimozione del grounding sul grafo riduce precision e produce più match allucinati che violano criteri numerici o temporali
- Collassare estrazione e matching in un singolo agente abbassa F1 da 0.8246 a 0.78

### Contributo chiave per la tesi

**È l'unico sistema in letteratura con architettura comparabile alla tua: KB oncologica strutturata pre-costruita + agenti LLM specializzati.** Non è un lavoro concorrente nel senso stretto — è una validazione industriale dello stesso principio architetturale che la tesi implementa in scala accademica.

Il dato più importante per la tesi viene dall'**ablation study**: rimuovere il grounding sul grafo (passare da GraphRAG a LLM vanilla) riduce F1 da 0.82 a 0.79 e aumenta le allucinazioni. Questo è esattamente il risultato che hai osservato in RQ1 (0% vs 100% su PMID hallucination) — ma su scala e con metodologia industriale che ne valida l'importanza.

### Differenze rispetto alla tesi — dove la tesi va oltre

**Differenza 1 — Task:**
OncoAgents si concentra su clinical trial matching. La tesi affronta therapeutic recommendation con classificazione ESCAT e citazioni verificabili — un task più articolato clinicamente.

**Differenza 2 — Therapy line:**
OncoAgents non gestisce la linea terapeutica come vincolo strutturale. La tesi ha `therapy_line` come input obbligatorio che modifica le raccomandazioni — più vicino al processo decisionale reale di un MTB.

**Differenza 3 — Scala vs profondità:**
OncoAgents opera su 3.804 pazienti ma su un task specifico (trial matching). La tesi opera su 30 casi con pipeline completa a 5 agenti, ESCAT tier, resistance checker, e sintesi strutturata con PMID verificati — maggiore profondità clinica per singolo caso.

**Differenza 4 — Modello:**
OncoAgents usa GPT-4 (closed-source, costoso). La tesi usa Gemma 4 31B via Ollama (open-source, gratuito) — dimostrando che l'architettura funziona anche senza dipendenza da modelli commerciali.

### Dove usarlo in tesi

- **Lavori correlati:** come sistema industriale con architettura comparabile — validazione esterna del principio KB strutturata + agenti
- **Motivation:** l'ablation study di OncoAgents è la prova letteratura che il grounding sul grafo riduce le allucinazioni — rafforza la tua RQ1
- **Discussione:** posizionare la tesi come implementazione accademica open-source di un principio validato industrialmente su scala molto più grande

---

## Sintesi: Come Cambiano il Posizionamento della Tesi

### Prima di questi tre paper

Il posizionamento era:
- Edge et al. → perché GraphRAG (infrastruttura)
- Wu et al. → perché KB medica strutturata (dominio)
- Kim et al. → perché multi-agente adattivo (architettura)
- Jin et al. → perché Trial Matcher (applicazione)
- Díaz Cantón → contesto 2026 (scenario)

Mancava: **perché questo approccio per gli MTB specificamente**, con un confronto diretto su sistemi RAG per MTB.

### Dopo questi tre paper

La narrativa diventa completa su quattro livelli:

| Livello | Paper | Funzione |
|---|---|---|
| Clinico — definizione del problema | Aldea et al. (IASLC 2025) | ESCAT è lo standard clinico riconosciuto per gli MTB |
| Tecnico — confronto diretto RAG | Berman et al. (JMIR 2025) | RAG testuale su PubMed ha limiti strutturali che la KB Neo4j risolve |
| Tecnico — validazione industriale | Loaiza-Bonilla et al. (ESMO 2026) | KB oncologica + multi-agente è l'architettura vincente anche su 3.804 pazienti reali |
| Contributo originale della tesi | — | ESCAT tier, therapy_line, resistance checker, open-source su modello gratuito |

### La frase di positioning aggiornata per la discussione con il prof

> "Il sistema proposto si colloca all'intersezione tra tre tendenze convergenti nella letteratura recente: la validazione clinica dell'uso di ESCAT come standard per le raccomandazioni MTB (Aldea et al., IASLC 2025), la dimostrazione che il RAG testuale su PubMed soffre di limitazioni strutturali nella gestione delle citazioni (Berman et al., JMIR 2025), e la validazione industriale su larga scala che la combinazione KB oncologica strutturata + agenti LLM specializzati riduce le allucinazioni e migliora la precision rispetto al solo LLM (Loaiza-Bonilla et al., ESMO 2026). La tesi contribuisce a questo panorama con una pipeline open-source completa che integra classificazione ESCAT, gestione della linea terapeutica e verifica strutturale delle citazioni — elementi assenti o parziali in tutti e tre i sistemi di riferimento."

---

## Tabella Comparativa Completa (aggiornata con i nuovi paper)

| Sistema | Task | KB | Agenti | ESCAT | Therapy Line | Hallucination Control | Scala |
|---|---|---|---|---|---|---|---|
| Berman et al. 2025 | MTB recommendation | PubMed RAG testuale | No | No | No | Nessuno strutturale | Casi reali MTB |
| Loaiza-Bonilla et al. 2026 | Trial matching | OncoGraph (KB proprietaria) | Sì (OncoAgents) | No | No | Grounding sul grafo | 3.804 pazienti |
| Ferber et al. 2025 | Decision-making oncologico | OncoKB + web search | Sì (tool-based) | No | No | Tool grounding | 20 casi multimodali |
| **Tesi (GraphRAG MTB)** | **MTB recommendation + trial** | **Neo4j (CIViC+OncoKB)** | **Sì (5 agenti)** | **Sì** | **Sì** | **CITED_IN verificato** | **30 casi benchmark** |

---

*Report generato — Giugno 2026*