# MTB-GraphRAG V3 — posizionamento scientifico

**Stato:** specifica congelata, non implementata. Baseline V2 al commit `03aa927`.

> **Nota sul runtime valutato Protocol 1.7.** Il posizionamento empirico della
> Final Evaluation è documentato in
> `docs/verifiable_pipeline/evaluated_runtime_architecture.md`. Per il runtime
> LIVE valutato, il contributo va descritto come **authority-separated evidence
> orchestration** con **document-aware bounded evidence selection**: non come due
> selector LIVE indipendenti, non come gates con soli due input e non come una
> modalità operativa LIVE/REPLAY selezionabile. Il replay appartiene soltanto
> alla ricerca/regressione.

---

## Tesi di posizionamento

> **MTB-GraphRAG V3 è una specializzazione evidence-centric e task-specifica di Medical
> Graph RAG per la ricostruzione, qualificazione e presentazione verificabile delle
> evidenze in precision oncology.**

L'unità di lavoro non è la domanda medica ma il **caso molecolare strutturato**; l'unità
di conoscenza non è il documento ma l'**EvidenceStatement clinicamente qualificato**;
l'output non è una risposta ma un **dossier claim-level destinato alla revisione umana**
in Molecular Tumor Board.

## Che cosa la V3 non è

Queste negazioni non sono cautela retorica: ciascuna esclude un'architettura che sarebbe
plausibile e che il sistema deliberatamente non adotta.

| Non è | Perché la distinzione conta |
| --- | --- |
| chatbot medico generale | l'input è un caso strutturato, non linguaggio libero |
| sistema autonomo di raccomandazione terapeutica | l'output si ferma all'evidenza qualificata; la raccomandazione resta alla MTB |
| sostituto della Molecular Tumor Board | il dossier è materiale *per* la board, e la revisione umana è un passo obbligatorio del flusso |
| motore di decisione clinica | non esiste alcuna funzione che produca una scelta terapeutica |
| semplice agente sopra Neo4j | il percorso principale è deterministico; l'agente si attiva solo dopo una decisione esplicita del sufficiency gate |
| sistema che risolve l'incompletezza del KG generando testo | l'assenza dal grafo produce astensione o candidato esterno in quarantena, mai contenuto generato |

L'ultima riga è quella che il pilota V2 ha reso concreta: **il 55% delle perdite osservate
nasce nel Knowledge Graph**, prima che qualunque modello entri in gioco. Un sistema che
colmasse quel vuoto generando testo produrrebbe un dossier più completo e meno vero.

## Tabella comparativa

| Dimensione | RAG documentale | Knowledge Graph QA | GraphRAG medico / MedGraphRAG | Agentic RAG | **MTB-GraphRAG V3** |
| --- | --- | --- | --- | --- | --- |
| **Dominio** | generale | generale | medico ampio | generale | **precision oncology, preparazione dossier MTB** |
| **Input** | domanda in linguaggio naturale | domanda su entità | domanda clinica | obiettivo | **Case Graph strutturato e de-identificato** |
| **Rappresentazione del caso** | assente | entità nominate | contesto testuale | stato dell'agente | **oggetto tipizzato: stadio, setting, linea, terapie precedenti, findings molecolari** |
| **Rappresentazione dell'evidenza** | chunk | triple | triple + comunità | passaggi recuperati | **EvidenceStatement qualificato con contesto clinico e provenienza** |
| **Fonti** | corpus documentale | KG | letteratura + terminologie | web / tool | **KG congelato + profili clinici delle fonti revisionati + candidati esterni in quarantena** |
| **Retrieval** | similarità vettoriale | pattern su grafo | traversal + riassunto di comunità | scelto dall'agente | **traversal oncologico tipizzato, deterministico e primo nel flusso** |
| **Aggiornamento** | reindicizzazione | rescrittura del grafo | reindicizzazione | on-demand | **snapshot versionato con fingerprint; import esterno solo dopo revisione umana** |
| **Uso dell'agente** | assente | assente | opzionale | centrale | **condizionale: solo dopo che il sufficiency gate lo ha richiesto, con trigger registrato** |
| **Provenance** | citazione al chunk | arco | mista | debole | **catena esplicita: statement → fonte → span → estrazione → revisore → snapshot → claim** |
| **Verifica** | assente o post-hoc | consistenza di schema | filtri di sicurezza | assente | **verifica strutturale + verifica claim-fonte, con repair ed escalation limitati** |
| **Applicabilità** | non modellata | non modellata | non modellata | non modellata | **confronto esplicito caso ↔ contesto della fonte, separato dallo stato documentale** |
| **Output** | risposta | risposta | risposta evidence-based | risposta | **dossier MTB claim-level con stato, conflitti, contesto mancante, astensione** |
| **Ruolo umano** | lettore | lettore | lettore | supervisore | **revisore obbligatorio; il flusso ha punti di escalation espliciti** |
| **Obiettivo sperimentale** | qualità della risposta | accuratezza fattuale | sicurezza e fondatezza | autonomia | **attribuzione del miglioramento ai singoli componenti** |

## La distinzione centrale

**Medical Graph RAG generale** risponde a una domanda medica costruendo contesto da
letteratura, documenti e terminologie, e produce una risposta evidence-based.

**MTB-GraphRAG V3** parte da un caso molecolare e clinico strutturato, recupera
EvidenceStatement qualificati con un traversal oncologico tipizzato, ne valuta
l'**applicabilità rispetto a quel caso**, e produce un dossier claim-level in cui ogni
affermazione è tracciabile e la revisione umana è esplicita.

Le due differenze che non si riducono a una questione di dominio:

**Applicabilità distinta da validità documentale.** Una fonte può sostenere pienamente
ciò che afferma e non riguardare il paziente. È il caso C1 del pilota: ADAURA e AURA3 sono
studi reali, correttamente citati, su popolazioni che non sono quella di un paziente in
prima linea senza T790M. Un sistema che le elimina sbaglia quanto uno che le presenta come
pertinenti. La V2 misura già `compatible_overstatement_rate` e nel pilota è **0.000** — non
ha mai presentato come applicabile una fonte non applicabile — ma
`applicability_status_accuracy` è **0.000**: non emette affatto il giudizio nella forma
richiesta. La V3 rende quel giudizio un contratto tipizzato.

**Qualificazione clinica come parte della rappresentazione, non della generazione.** Nel
KG attuale setting, linea di terapia, stadio e resezione **non esistono**: i 24
qualificatori del pilota risultano tutti assenti perché lo schema non li modella. Oggi
vivono solo nei `SourceClinicalProfile` annotati a mano. La V3 li promuove a campi di primo
livello dell'EvidenceStatement, con provenienza, invece di lasciarli a un'estrazione
testuale a valle.

## Che cosa la V3 eredita dalla V2

Il contributo non è una riscrittura. Il backbone di controllo resta, ed è la parte che il
pilota ha mostrato funzionare:

- `citation_accuracy` **1.000** su 24 run: nessuna citazione inventata;
- `negative_case_accuracy` **1.000**: il caso RMI2 si astiene in tutte e sei le run;
- reporting strutturato contro sintesi libera, a retrieval congelato identico:
  `structural_coverage` **1.000 contro 0.325**, `unsupported_claim_rate` **0.000 contro
  0.036**.

Questi risultati sono **osservazioni tecniche su quattro casi development**, non una
validazione clinica, e la V3 li assume come baseline da preservare — non come traguardo
raggiunto.

## Contributo positivo della V3

Non un audit degli errori della V2, ma cinque aggiunte:

1. **Case Graph** — il caso come oggetto tipizzato, con l'assenza rappresentata
   esplicitamente invece che dedotta.
2. **Evidence Statement Layer** — la proposizione clinicamente qualificata come unità di
   conoscenza, al posto della coppia variante-farmaco.
3. **Clinical Qualification Layer** — il confronto caso ↔ fonte come contratto
   deterministico con dimensioni dichiarate, non come output libero di un modello.
4. **Sufficiency Gate + refinement condizionale** — l'agente come risposta a
   un'insufficienza rilevata, non come architettura alternativa. Il pilota mostra perché:
   sui quattro casi il planner agentico ha riordinato gli strumenti senza cambiare il
   retrieval, costando 5 chiamate e una latenza 5× (10,1 s contro 2,1 s).
5. **Evidence expansion controllata** — le fonti esterne entrano come *candidati in
   quarantena*, mai come evidenza consolidata, e la promozione richiede un'azione umana.

## Bibliografia

**Nessun riferimento è stato verificato in questa sessione.** L'ambiente non ha accesso
alla rete per il controllo bibliografico, quindi l'intera lista è nella seconda categoria.
Inserirla in tesi senza verifica sarebbe un errore, e ciascuna voce va controllata su
fonte primaria.

### Riferimenti verificati

*(vuota — nessuna verifica possibile in questa sessione)*

### Riferimenti da verificare prima dell'inserimento in tesi

| # | Riferimento presunto | Che cosa deve sostenere | Da controllare |
| --- | --- | --- | --- |
| R1 | Wu et al., *Medical Graph RAG*, arXiv 2024 | il termine MedGraphRAG e il suo perimetro | autori, anno, identificatore arXiv, claim effettivo |
| R2 | Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, arXiv 2024 | GraphRAG generale e riassunto di comunità | autori, anno, identificatore |
| R3 | Griffith et al., *CIViC*, Nature Genetics 2017 | la knowledge base che alimenta lo snapshot | autori, volume, pagine, DOI |
| R4 | Chakravarty et al., *OncoKB*, JCO Precision Oncology 2017 | tassonomia dei livelli di evidenza | autori, DOI, definizione dei livelli |
| R5 | Li et al., *Standards and Guidelines for the Interpretation and Reporting of Sequence Variants in Cancer* (AMP/ASCO/CAP), J Mol Diagn 2017 | tiering delle varianti somatiche | autori, DOI, definizione dei tier |
| R6 | Mateo et al., *ESCAT*, Annals of Oncology 2018 | scala ESMO di actionability | autori, DOI, definizione dei livelli |
| R7 | Documentazione ClinicalTrials.gov API | campi dei trial e loro semantica | URL ufficiale, versione API |
| R8 | Documentazione NCBI E-utilities | identificatori PMID/PMCID | URL ufficiale |
| R9 | Position paper su composizione e workflow delle Molecular Tumor Board | il ruolo della board e il punto di inserimento del dossier | società scientifica, anno, DOI |

**TODO bibliografico.** Prima della stesura della tesi: verificare ogni voce su fonte
primaria; sostituire quelle non confermate; per R4, R5 e R6 riportare le definizioni
originali dei livelli, perché la V3 dichiara di **non** convertire silenziosamente scale
incompatibili e quella promessa va sostenuta citando le scale vere.

## Open Decisions

| # | Decisione | Tipo | Note |
| --- | --- | --- | --- |
| P1 | Quale tassonomia dei livelli di evidenza adottare come `normalized_tier` | **richiede revisione clinica** + verifica bibliografica | candidate: OncoKB, ESCAT, AMP/ASCO/CAP. La V3 preserva l'originale, ma il tier normalizzato serve all'ordinamento |
| P2 | Se posizionare la V3 rispetto a MedGraphRAG come *specializzazione* o come *architettura distinta* | **necessaria prima dell'implementazione** | incide sulla struttura del capitolo e sulle baseline da implementare |
| P3 | Quali società scientifiche citare per il workflow MTB | verifica bibliografica | dipende dal contesto geografico della tesi |
| P4 | Se includere Baseline 0 (RAG documentale) nella tesi o solo nel protocollo | **rimandabile** | costa un'implementazione; senza, RQ2 resta parzialmente non risposta |
| P5 | Terminologia italiana o inglese per i termini del modello nei documenti di tesi | ingegneristica / editoriale | il codice è in inglese, la documentazione in italiano |
