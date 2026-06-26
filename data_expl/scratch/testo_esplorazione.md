# 📊 Esplorazione Quantitativa del Knowledge Graph Oncologico (GraphRAG)
### *Studio Analitico, Diagnostica e Copertura Terapeutica per il Molecular Tumor Board*

---

Questo Notebook esegue un'analisi statistica e diagnostica sul **Knowledge Graph (KB) oncologico** costruito a partire dai dati puliti situati nella cartella `Clean_Graph_Data`.

L'obiettivo è estrarre metriche chiave suddivise nelle seguenti macro-aree:
1. **Struttura della KB**: Distribuzione dei nodi, densità del grafo, forza delle evidenze (CIViC).
2. **Copertura Clinica**: Geni e farmaci più documentati, patologie e tipi di evidenza (Predictive vs Diagnostic vs Prognostic).
3. **Azionabilità Clinica della KB (Copertura di Evidenze ad Alto Rigore)**: Quota di conoscenza azionabile ad alto rigore, classificazione ESCAT-like e copertura dei trial per gene.
4. **Individuazione dei Gap**: Varianti senza evidenza Predictive e farmaci esclusi nei trial.
5. **Analisi per il Trial Matcher**: Distribuzione delle fasi e dei geni/farmaci più rappresentati nei trial clinici.
6. **Analisi Grafo-Nativa su Neo4j (Cypher)**: Studio dei percorsi biologico-clinici a hop multipli, calcolo della centralità terapeutica e query contestuali sul caso paziente.
7. **Matrice Gene-Tumore (Co-occorrenza)**: Relazione a doppia entrata tra i top biomarcatori e le patologie.
8. **Dataset di Benchmark Clinico (30 Casi MTB)**: Caratterizzazione dei casi clinici reali per la validazione indipendente.

---


### 📐 Schema Concettuale del Knowledge Graph (Data Model)
Il Knowledge Graph oncologico mappa in modo strutturato e integrato le relazioni biologiche e cliniche tra geni, varianti, profili molecolari, evidenze terapeutiche, farmaci, companion diagnostics e trial clinici.

Di seguito viene visualizzato lo **schema concettuale in tempo reale** interrogando direttamente l'istanza locale di Neo4j. Se il database locale non è attivo, il sistema utilizzerà automaticamente uno schema pre-caricato di fallback per garantire la visualizzazione corretta.


### 🛠️ Inizializzazione dell'Ambiente e Configurazione degli Stili
Questo blocco di codice gestisce l'importazione delle librerie fondamentali per l'analisi dei dati (`pandas`, `numpy`), la visualizzazione (`matplotlib`, `seaborn`), la connettività del database a grafi (`neo4j`) e il rendering di interfacce utente in modalità CLI/Jupyter (`rich`). 

**🔬 Obiettivo Scientifico**: Configurare una console interattiva con larghezza ottimizzata e impostare una palette grafica ad alto contrasto per Seaborn e Matplotlib, garantendo che tutti i grafici siano perfettamente leggibili e conformi agli standard di una pubblicazione scientifica.


### 📥 Ingestione e Caricamento dei Dataset della KB
In questa fase carichiamo in memoria i nodi e gli archi che compongono il Knowledge Graph oncologico a partire dai file CSV puliti.

**🔬 Obiettivo Scientifico**: Eseguire l'ingestione strutturata di nodi e relazioni (geni, varianti, profili molecolari, evidenze, farmaci, companion diagnostics e trial clinici) verificando in tempo reale l'integrità referenziale del grafo e stampando una sintesi numerica completa tramite pannelli `Rich`.


## 1. Struttura del Knowledge Graph (KB)
*Analisi qualitativa e quantitativa della geometria del grafo, della densità dei collegamenti e della distribuzione delle evidenze cliniche.*


### 📊 1.1 Distribuzione Quantitativa dei Nodi nella KB
Un Knowledge Graph oncologico bilanciato deve possedere una chiara distribuzione dei suoi componenti clinico-biologici.

**🔬 Obiettivo Scientifico**: Quantificare e classificare ciascuna tipologia di entità (nodi) per comprendere la composizione strutturale del grafo, evidenziando il rapporto percentuale tramite una tabella Rich e visualizzando i rapporti quantitativi tramite un barplot Seaborn ordinato.


### 🧬 1.2 Geometria del Grafo e Connessioni Biologiche
L'analisi dei gradi di connessione ci permette di individuare i "punti caldi" (hotspots) all'interno del grafo, come i geni con più varianti o i profili molecolari con maggior numero di evidenze cliniche registrate.

**🔬 Obiettivo Scientifico**: Misurare la capillarità delle relazioni ed estrarre la classifica dei top 10 geni per varianti e top 10 profili molecolari clinicamente più rilevanti per identificare i biomarcatori dominanti.


### 🧪 1.3 Forza Clinica del Grafo: Distribuzione dei Livelli di Evidenza CIViC
Il rigore scientifico del sistema di supporto alle decisioni (MTB) dipende dalla forza delle prove accumulate in letteratura.

**🔬 Obiettivo Scientifico**: Categorizzare le evidenze presenti nel grafo secondo i livelli CIViC (da A = massimo rigore clinico / approvato FDA, fino a E = caso clinico singolo). Questa distribuzione permette di comprendere onestamente quanta parte della KB sia basata su standard solidi rispetto a studi preliminari o preclinici.


### 📅 1.4 Distribuzione Temporale e Latenza delle Fonti (Obsolescenza dei Dati)
La tesi sostiene che i dati clinici statici invecchiano rapidamente, rendendo cruciale l'integrazione di sistemi live ed agenti autonomi.

**🔬 Obiettivo Scientifico**: Analizzare empiricamente la datazione delle pubblicazioni scientifiche che compongono il grafo per misurare la latenza della conoscenza e quantificare la quota di studi obsoleti (> 5 anni), tracciando la curva di invecchiamento del dato statico tramite un istogramma Seaborn.


## 2. Capire la Copertura Clinica
*Analisi scientifica della KB: quali geni, farmaci e tumori sono più rappresentati all'interno della letteratura clinica curata.*


### 🧬 2.1 Top 20 Geni per Copertura di Evidenze Cliniche
Identificare quali geni accumulano la maggior parte delle evidenze cliniche ci consente di calibrare la base di conoscenza del Molecular Tumor Board.

**🔬 Obiettivo Scientifico**: Attraversare le relazioni `Evidence ➔ MolecularProfile ➔ Variant ➔ Gene` in Pandas per aggregare e ordinare i 20 biomarcatori più documentati, visualizzando il loro peso relativo nella KB.


### 💊 2.2 Top 20 Terapie Farmacologiche nella KB
Questo blocco analizza i farmaci oncologici (predittivi) che possiedono il maggior numero di evidenze terapeutiche associate.

**🔬 Obiettivo Scientifico**: Mappare la copertura terapeutica unendo le evidenze con l'anagrafica dei farmaci, estraendo la classifica dei top 20 principi attivi più testati all'interno della base di conoscenza.


### 🩺 2.3 Patologie Oncologiche e Scopi delle Evidenze Cliniche
Un'analisi completa deve comprendere quali tipi tumorali sono maggiormente rappresentati e per quale scopo clinico (predittivo, diagnostico o prognostico).

**🔬 Obiettivo Scientifico**: Estrarre le 15 patologie più documentate e visualizzare la suddivisione delle evidenze per scopo clinico tramite un doppio grafico coordinato (barplot Seaborn + pie chart delle percentuali).


### 🩺 2.4 Audit della Qualità del Dato e Completezza della KB
Prima di procedere all'estrazione del benchmark o all'interrogazione del database a grafi, è fondamentale auditare onestamente lo stato di salute dei dati.

**🔬 Obiettivo Scientifico**: Eseguire una diagnostica quantitativa della completezza della base di conoscenza (valori nulli nei campi chiave) ed evidenziare l'effetto risolutivo della normalizzazione delle patologie rispetto alle stringhe grezze, calcolando la frammentazione terminologica rimossa.


## 3. Azionabilità Clinica della KB (Copertura di Evidenza ad Alto Rigore)
*Analisi di azionabilità clinica del grafo: quota di conoscenza azionabile ad alto rigore e classificazione ESCAT-like.*


### 🏆 3.1 Classificazione ESCAT-like ed Evidenze ad Alto Rigore
Per comprendere il livello di solidità scientifica della base di conoscenza clinica, è fondamentale quantificare il sottoinsieme di evidenze ad alto rigore.

**🔬 Obiettivo Scientifico**: Mappare i livelli di evidenza CIViC sulla tassonomia standard ESCAT (Tier I-IV) e quantificare il sottoinsieme di profili molecolari con evidenze di livello A, quantificando la quota di conoscenza clinicamente azionabile ad alto rigore presente nella KB.

**💡 Giustificazione Clinica della Tassonomia ESCAT-like**:
Il sistema di cura nativo di CIViC classifica le evidenze secondo le linee guida *AMP/ASCO/CAP* (Tier I: Forte rilevanza clinica, Tier II: Potenziale rilevanza, Tier III: Rilevanza incerta, Tier IV: Benigne/Comuni).
Tuttavia, all'interno del Molecular Tumor Board (MTB) e ai fini dello sviluppo di un sistema di supporto decisionale (GraphRAG), abbiamo scelto di implementare una mappatura **ESCAT-like** ispirata alla tassonomia *ESCAT (ESMO Scale for Clinical Actionability of molecular Targets)*.
Mentre AMP/ASCO/CAP valuta la forza intrinseca dell'evidenza biologica, **ESCAT classifica l'alterazione genomica in base all'efficacia clinica del match alterazione-farmaco in uno specifico tipo di tumore**.
Questa è la classificazione d'elezione per i clinici dell'MTB per pesare l'azionabilità terapeutica.
*Limite dichiarato*: Questa mappatura è definita "ESCAT-like" poiché CIViC ed OncoKB non assegnano direttamente i livelli ESCAT ufficiali; pertanto, mappare i livelli di entrambe le fonti (CIViC A/B ed OncoKB LEVEL_1/LEVEL_2) sotto il medesimo "Tier I" rappresenta una semplificazione clinica necessaria per garantire stabilità algoritmica al MoE Router del sistema agentico, riconciliando le due tassonomie.


### 🔬 3.2 Copertura dei Trial Clinici sui Geni del Grafo
Valutare quanti dei geni registrati nella base di conoscenza possiedono almeno un trial clinico aperto ci permette di misurare l'utilità pratica del sistema di matching terapeutico.

**🔬 Obiettivo Scientifico**: Calcolare l'intersezione tra l'anagrafica dei geni e l'elenco dei trial clinici del grafo, calcolandone la percentuale esatta di copertura.


### 📋 3.3 Direzione Clinica e Significato Terapeutico delle Evidenze
La sicurezza del paziente e la precisione dell'MTB dipendono dal distinguere accuratamente se un'associazione supporti la sensibilità o indichi una resistenza farmacologica.

**🔬 Obiettivo Scientifico**: Costruire una tabella di co-occorrenza (crosstab) tra la direzione clinica delle evidenze (`evidence_direction`: *Supports* vs *Does Not Support*) ed il loro significato terapeutico (`significance`: *Sensitivity/Response*, *Resistance*, *Diagnostic*, *Prognostic*) per analizzare la composizione della conoscenza oncologica.


## 4. Individuazione dei Gap (Zone d'Ombra)
*Analisi delle varianti cliniche orfane (prive di evidenze terapeutiche predittive) e dei farmaci dei trial clinici non mappati contro le ontologie principali.*


### ⚠️ 4.1 Varianti Cliniche Orfane e Disallineamenti nei Trial
Identificare le varianti sprovviste di terapie predittive e i farmaci dei trial non mappati nelle ontologie principali ci permette di evidenziare i limiti informativi attuali del grafo.

**🔬 Obiettivo Scientifico**: Estrarre le percentuali di varianti prive di evidenza terapeutica (`Predictive`) e quantificare i farmaci sperimentali dei trial clinici non presenti in DGIdb/FDA, isolando i gap biologici ed ETL del sistema.


## 5. Analisi per il Trial Matcher
*Analisi dei dati dei trial clinici del grafo (fasi, farmaci e geni) per la calibrazione fine dell'agente Trial Matcher.*


### 📅 5.1 Analisi Strutturale dei Trial Clinici per la Calibrazione del Matcher
Per calibrare l'agente Trial Matcher, è essenziale mappare le fasi dei trial aperti, i geni target più studiati e i farmaci sperimentali più frequenti.

**🔬 Obiettivo Scientifico**: Generare classifiche dettagliate dei geni e farmaci con più trial attivi, e tracciare la distribuzione delle fasi dei trial clinici tramite tabelle Rich e doppi barplot Seaborn.


## 6. Analisi Grafo-Nativa su Neo4j (Cypher)
*Integrazione ibrida del Graph Database locale Neo4j 'GraphRAGTesi' nel notebook. Sfruttiamo le potenzialità delle query Cypher a Hop multipli per calcolare centralità biologica, raggiungibilità e percorsi terapeutici complessi.*


### 🔌 6.1 Connettività Ibrida e Configurazione del Graph Database Neo4j
L'integrazione di Neo4j consente di effettuare analisi strutturali complesse direttamente sul grafo locale.

**🔬 Obiettivo Scientifico**: Inizializzare la connessione al DBMS `GraphRAGTesi` in esecuzione su `bolt://localhost:7687` (con fallback su `neo4j://localhost:7687`) definendo una funzione helper robusta per convertire i risultati delle query Cypher in DataFrame Pandas pronti per il rendering.


### 🔗 6.2 Estrazione di Cammini Clinici Complessi a 6-Hop con Cypher
Questo blocco dimostra la superiorità di Cypher nel recupero di cammini relazionali biologico-clinici a hop multipli, integrando ora anche i nuovi nodi **Disease** e **Publication**.

**🔬 Obiettivo Scientifico**: Eseguire una query Cypher che attraversa istantaneamente `Gene ➔ Variant ➔ MolecularProfile ➔ Evidence ➔ Drug / Disease / Publication` in un singolo cammino biologico, visualizzando la query in formato Monokai e stampando i primi 10 percorsi terapeutici consolidati arricchiti con l'indicazione del tumore e del codice scientifico di riferimento (PMID).


### ⚡ 6.2b Benchmark di Performance: Pandas Join vs Cypher Graph Traversal
Per validare scientificamente l'efficacia dell'approccio a grafi in tesi, è fondamentale misurarne quantitativamente le performance rispetto a un approccio tabulare relazionale classico.

**🔬 Obiettivo Scientifico**: Eseguire lo stesso cammino di recupero a 6-Hop (Gene ➔ Variant ➔ MP ➔ Evidence ➔ Drug / Disease / Publication) sia in memoria tramite Pandas (hash join sequenziali con `.merge()`), sia sul DBMS a grafi Neo4j. Misurare ed esporre i rispettivi tempi di esecuzione medi in millisecondi per fornire prove empiriche della superiorità del database a grafi su cammini ad alto numero di hop.


### 🎯 6.3 Centralità Terapeutica e Raggio d'Azione dei Geni Hub
Identificare i geni con il maggior numero di connessioni a farmaci distinti ci permette di comprendere la centralità biologica del grafo.

**🔬 Obiettivo Scientifico**: Eseguire una query Cypher con `OPTIONAL MATCH` che somma i farmaci raggiungibili sia attraverso la **catena clinica CIViC** (4-Hop: Gene → Variant → MolecularProfile → Evidence → Drug) sia attraverso le **interazioni dirette DGIdb** (1-Hop: Gene → Drug). L'uso di `OPTIONAL MATCH` garantisce che vengano inclusi anche i geni connessi a un solo tipo di sorgente, evitando di perdere informazioni rilevanti.


### 🩺 6.4 Caso d'Uso Clinico #1: Raccomandazioni Terapeutiche EGFR
Simuliamo l'interrogazione del grafo per un paziente reale avente una mutazione del gene EGFR.

**🔬 Obiettivo Scientifico**: Estrarre all'istante tutte le varianti di EGFR, i farmaci associati e la forza delle evidenze per supportare la decisione clinica del Molecular Tumor Board in tempo reale.


### ⚠️ 6.5 Caso d'Uso Clinico #2: Analisi delle Resistenze BRAF V600E
Un Molecular Tumor Board deve conoscere non solo i farmaci efficaci ma anche le **resistenze acquisite**. La variante BRAF V600E è particolarmente istruttiva: è sensibile a inibitori BRAF nel melanoma (vemurafenib, dabrafenib) ma conferisce **resistenza** agli anticorpi anti-EGFR (cetuximab, panitumumab) nel carcinoma colorettale.

**🔬 Obiettivo Scientifico**: Dimostrare la capacità del grafo di rilevare automaticamente i farmaci che conferiscono resistenza, filtrando il campo `significance` per il valore `Resistance`. Questo è un caso d'uso clinicamente critico per evitare prescrizioni inappropriate.


### 🧬 6.6 Studio Topologico: Interazioni Dirette (1-Hop) vs Catene Cliniche (4-Hop)
Questo blocco analizza la ricchezza strutturale del grafo, confrontando le connessioni dirette gene-farmaco con quelle mediate dalle varianti e dalle evidenze.

**🔬 Obiettivo Scientifico**: Calcolare tramite query Cypher avanzata il rapporto tra farmaci connessi direttamente (DGIdb) e farmaci raggiungibili solo tramite la catena clinica molecolare (CIViC), evidenziando l'utilità delle relazioni a hop multipli. L'uso di `OPTIONAL MATCH` garantisce che vengano inclusi anche i geni connessi a un solo tipo di sorgente.


## 7. Matrice Gene-Tumore (Co-occorrenza)
*Mappatura delle associazioni tra le mutazioni dei top geni oncologici e le principali patologie tumorali per identificare la rilevanza clinica dei biomarcatori.*


### 📊 7.1 Matrice di Associazione e Co-occorrenza Gene-Tumore (Heatmap)
L'associazione a doppia entrata tra geni mutati e patologie tumorali evidenzia la specificità oncologica dei biomarcatori.

**🔬 Obiettivo Scientifico**: Costruire una tabella di co-occorrenza (crosstab) tra i top 15 geni e i top 15 tumori per evidenza clinica, visualizzandola in formato Rich Table e tramite una Heatmap premium Seaborn.


## 8. Dataset di Benchmark Clinico (30 Casi MTB)
*Caratterizzazione del dataset di benchmark reale costruito su pubblicazioni da NEJM, JCO, Lancet Oncology e ESMO Open, con ground-truth terapeutica verificata da esperti clinici.*


### 📋 8.1 Caricamento e Panoramica dei 30 Casi Benchmark

Il benchmark è composto da **30 casi clinici reali** estratti da articoli pubblicati su riviste peer-reviewed di primo piano. Per ciascun caso sono definiti:
- Il **profilo molecolare** (gene + variante)
- Il **tipo tumorale specifico**
- La **terapia attesa (ground-truth)**: farmaco o combinazione raccomandato da linee guida o trial registrativi
- Il **livello ESCAT** assegnato dagli autori
- La **categoria** del caso (baseline, resistenza, off-label, nuovo target, tumor-agnostic, biomarcatore)

Questo CSV costituisce la **unica fonte di verità** per la valutazione del sistema agentico.


### 📊 8.2 Distribuzione per Categoria e Livello ESCAT

Il benchmark è stato costruito per coprire diversi scenari clinici reali che il sistema agentico dovrà gestire, con difficoltà crescente rispetto ai casi baseline.


## 9. Integrazione di OncoKB & Routing Multi-Sorgente (MoE Router)
*Descrizione dell'architettura di integrazione multi-sorgente e ingegnerizzazione del grafo con evidenze cliniche ad alto rigore da OncoKB. Questa sezione documenta il processo di iniezione di biomarcatori globali e varianti rare, confrontando le sorgenti.*

### 🛠️ 9.1 Il Problema dei Gap Strutturali in CIViC
Nelle sezioni precedenti (Sezione 4), l'audit preliminare ha evidenziato dei **limiti strutturali severi** nel database CIViC:
1. **Assenza di Biomarcatori Globali**: Entità cliniche non-classiche come `MSI-High` (Instabilità dei Microsatelliti) e `TMB-High` (Tumor Mutational Burden-High) non mappano su un singolo gene/variante classico in CIViC, rendendo impossibile per un agente MTB raccomandare immunoterapie tumor-agnostiche (es. Pembrolizumab) basandosi solo su di esso.
2. **Scarsa Documentazione delle Resistenze Rare**: Varianti cliniche cruciali come `ALK G1202R` (principale mutazione di resistenza all'Alectinib nel tumore del polmone) contengono in CIViC solo report aneddotici o clinicamente fuorvianti (es. Lorlatinib come resistenza nel Mesotelioma, Livello C), omettendo il reale standard terapeutico approvato (Lorlatinib, ESCAT Livello I-A).

Per risolvere questi limiti metodologici e clinici, abbiamo sviluppato una pipeline di **enrichment automatico basata sulle API di OncoKB** (Academic Token `a5e4ab21-1ee2-4428-b2f2-363548057b0c`).

### 🧬 9.2 Il Modello "Other Biomarkers" per Firme Genomiche Globali
In OncoKB, i biomarcatori globali sono classificati sotto un'entità speciale `hugoSymbol: "Other Biomarkers"` con `entrezGeneId: -2`. Abbiamo esteso il data model del nostro Knowledge Graph introducendo:
- Un nodo **Gene fittizio** `Other Biomarkers` (entrez_id: -2)
- Nodi **Variant e MolecularProfile** dedicati per `MSI-High` e `TMB-High`
- **17 nuove evidenze terapeutiche** ad alto rigore collegate a inibitori di checkpoint immunologici (Pembrolizumab, Nivolumab, Ipilimumab, Dostarlimab) e inibitori ALK di terza generazione (Lorlatinib, Neladalkib).


### ⚖️ 9.3 Contrasto Clinico-Topologico: CIViC vs OncoKB (Il caso ALK G1202R)
Il valore scientifico dell'approccio multi-sorgente emerge con eccezionale chiarezza analizzando la variante **ALK G1202R** (NSCLC).
- In **CIViC**: L'unica evidenza associava Lorlatinib come **Resistente** in un tumore diverso (*Mesotelioma*, livello C). Un agente MTB che interroga solo CIViC avrebbe sconsigliato il farmaco o mancato l'associazione corretta.
- In **OncoKB**: L'integrazione inserisce la corretta sensibilità standard di cura (Lorlatinib, **LEVEL_2** in *NSCLC*), più un farmaco sperimentale di nuova generazione (*Neladalkib*, **LEVEL_3A**) e le resistenze sistemiche ai farmaci di generazioni precedenti (Crizotinib, Ceritinib, Alectinib, Brigatinib normalizzati a **LEVEL_R2**).

Interroghiamo il grafo per confrontare in tempo reale queste evidenze contrapposte sullo stesso nodo Variante!


### 🔀 9.4 Architettura del MoE Router (Mixture of Experts)
L'esistenza di più fonti solleva una sfida: come deve interrogare il grafo il sistema agentico?
Abbiamo implementato una logica di **Routing Ibrido (Mixture of Experts - MoE)**:
1. **Query di Screening Globale (Biomarker Expert)**: Quando il profilo clinico presenta biomarcatori funzionali (`MSI-High` o `TMB-High`), il Router instrada la query direttamente verso il gene fittizio `Other Biomarkers` (entrez_id: -2), raccogliendo le evidenze ad alto rigore da OncoKB.
2. **Query di Sensibilità Standard (CIViC + OncoKB Expert)**: Per varianti puntiformi (es. `EGFR L858R`), il Router raccoglie ed effettua il merging delle evidenze da entrambe le fonti, dando priorità ai livelli regolatori (OncoKB LEVEL_1/2) rispetto ai dati pre-clinici (CIViC C/D).
3. **Query delle Resistenze (Safety Expert)**: In caso di mutazioni secondarie di fuga (es. `ALK G1202R` o `EGFR T790M`), il Router consulta sistematicamente le evidenze di resistenza per bloccare la prescrizione di farmaci inappropriati (es. Alectinib) e indicare il corretto farmaco di salvataggio (es. Lorlatinib).


## 10. Audit di Copertura del Benchmark sul Grafo
*Verifica sistematica che la KB contenga il percorso Gene➔Variante➔Evidenza➔Farmaco per ciascuno dei 30 casi benchmark. Classifica ogni caso come COVERED / PARTIAL / GAP, indica la sorgente della copertura (CIViC, OncoKB o Entrambi) e analizza i risultati.*


### 🔍 10.1 Metodologia e Strategie di Query Integrata
L'audit usa tre strategie distinte in base alla natura della variante:

- **Standard** (22 casi): percorso classico `Gene → HAS_VARIANT → Variant → IN_MOLECULAR_PROFILE → MolecularProfile → HAS_EVIDENCE → Evidence → TARGETS_DRUG → Drug`, con match flessibile sul nome della variante.
- **Fusion** (6 casi: ALK, BCR-ABL1, RET, NTRK1, FGFR2, ROS1): le fusioni in CIViC sono rappresentate a livello di MolecularProfile (es. "ALK Fusion"), non come coppie Gene→Variant classiche. Query diretta su `mp.name CONTAINS gene AND CONTAINS 'Fusion'`.
- **Biomarker** (2 casi: MSI-High, TMB-High): biomarcatori funzionali globali. Ricerca su nomi di Variant e MolecularProfile, con routing verso il gene fittizio `Other Biomarkers` per i dati OncoKB.

**Criteri di classificazione:**
- ✅ **COVERED**: almeno un farmaco (o combinazione) trovato in evidenze Predictive+Sensitivity con tumore compatibile.
- ⚠️ **PARTIAL**: farmaco presente ma tumore non corrispondente (off-label) o combinazione terapeutica incompleta (es. ERBB2 Amp).
- ❌ **GAP**: nessun farmaco atteso trovato nella KB.


### 🔍 10.3 Query Cypher per Verifica Manuale su Neo4j
Le query seguenti replicano le tre strategie dell'audit direttamente su Neo4j. Eseguile su Neo4j Desktop (GraphRAGTesi) per verificare i casi dubbi o HIGH-RISK e confrontare i risultati con l'analisi pandas.


### 🔚 Chiusura della Connessione Neo4j
Per una corretta gestione delle risorse, chiudiamo esplicitamente il driver Neo4j alla fine del notebook.
