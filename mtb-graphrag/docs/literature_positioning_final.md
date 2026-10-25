# Literature positioning

## Contesto

I Molecular Tumor Board (MTB) devono integrare dati clinici, alterazioni molecolari, conoscenza oncologica in evoluzione e fonti eterogenee. Tsimberidou et al. descrivono questa complessità e il ruolo crescente di piattaforme digitali nel lavoro dei MTB, senza ridurre l’interpretazione molecolare a una decisione automatica [1]. Tamborero et al. mostrano come l’integrazione strutturata e il reporting automatizzato possano sostenere la discussione multidisciplinare [2]. Perera-Bel et al. collegano in modo esplicito alterazioni somatiche, conoscenza pubblica ed evidence-driven reporting [3].

Questi lavori motivano il prodotto scelto in questa tesi: non una risposta narrativa libera, ma un dossier strutturato nel quale ogni associazione conserva origine, significato e limiti verificabili.

## Knowledge base oncologiche e relazioni eterogenee

CIViC rappresenta evidenze cliniche differenti — terapeutiche, diagnostiche, prognostiche e predisponenti — con provenance e interpretazione curate [4]. OncoKB mostra il valore della strutturazione per variante, contesto tumorale e livello di evidenza [5]. Le knowledge base non sono quindi semplici collezioni di documenti: modellano entità e relazioni con semantiche diverse.

Questa tesi assume il Knowledge Graph come livello strutturato che propone le relazioni pertinenti al caso. La relazione non viene però trattata automaticamente come verità documentale. La sua provenance determina una delle tre elaborazioni: ritorno al paper, acquisizione del record di trial oppure conservazione trasparente come conoscenza disponibile solo nel grafo.

Il recente Knowledge Connector colloca dati del paziente, conoscenza mondiale, associazioni di biomarcatori e documentazione MTB nello stesso processo di precision oncology [6]. Il presente lavoro si posiziona nella stessa direzione generale, ma con un obiettivo più circoscritto: rendere esplicita e verificabile la trasformazione da relazione del grafo a voce del dossier.

## LLM e grounding

L’uso di retrieval e LLM nei MTB è già oggetto di ricerca. Berman et al. studiano un sistema RAG per suggerimenti terapeutici e riportano che il 17% degli articoli citati risultava allucinato [7]. Questo dato non dimostra superiorità del sistema qui proposto e non è usato come confronto prestazionale. Motiva invece una scelta conservativa di architettura: l’LLM non è una fonte e non è l’autorità finale.

Nel core gli LLM hanno due ruoli limitati:

1. strutturare i fatti esplicitamente presenti nel caso clinico;
2. leggere estratti già selezionati di un paper e restituire una citazione letterale con osservazioni strutturate.

La selezione delle candidate, la classificazione della provenance, la validazione della quote, il confronto con la specificità della relazione e la costruzione del dossier sono deterministici. I trial restano associazioni a record NCT, non prove di efficacia. Le relazioni senza identificatore documentale non ricevono una fonte inventata.

## Differenza rispetto a un RAG classico

Un RAG classico segue tipicamente il percorso query → retrieval documentale → risposta LLM. Qui il percorso è caso clinico → `CaseContext` → relazioni del Knowledge Graph → strategia specifica per provenance → dossier deterministico.

Il Knowledge Graph non è soltanto un indice per recuperare chunk. Determina:

- quali associazioni strutturate considerare;
- quale relazione rappresentano;
- quale provenance possiedono;
- quale forma di verifica è applicabile.

Il documento viene interrogato soltanto quando la GCA indica un PMID. Un NCT attiva un resolver strutturato. L’assenza di un identificatore attiva una rappresentazione KG-only. La separazione limita l’overclaim e rende osservabile la distanza tra conoscenza grafica e supporto nella fonte.

## Contribution statement

> This work investigates a relation-aware architecture for transforming heterogeneous oncology knowledge-graph relations into traceable Molecular Tumor Board evidence reports. The architecture preserves graph provenance, grounds document-backed relations in their primary sources, keeps clinical-trial associations distinct from efficacy evidence, and explicitly identifies relations for which document-level verification is unavailable.

> Questo lavoro studia un’architettura relation-aware per trasformare relazioni eterogenee di un Knowledge Graph oncologico in report di evidenza tracciabili per Molecular Tumor Board. L’architettura preserva la provenance del grafo, collega le relazioni document-backed alle fonti primarie, mantiene le associazioni a trial clinici distinte dalle prove di efficacia e identifica esplicitamente le relazioni per cui non è disponibile una verifica a livello documentale.

## Posizionamento prudente

Il lavoro non propone un nuovo algoritmo clinico, un sistema autonomo di raccomandazione, un sostituto del MTB o una dimostrazione di migliori outcome clinici. Propone un’architettura KG-grounded e relation-aware che trasforma relazioni oncologiche strutturate in un dossier tracciabile, distinguendo conoscenza del grafo, provenance documentale, metadati dei trial e supporto effettivamente verificabile nel paper.

## Riferimenti

1. Tsimberidou AM et al. *Molecular tumour boards — current and future considerations for precision oncology*. Nature Reviews Clinical Oncology. 2023;20:843–863. [DOI: 10.1038/s41571-023-00824-4](https://doi.org/10.1038/s41571-023-00824-4). PMID 37845306.
2. Tamborero D et al. *The Molecular Tumor Board Portal supports clinical decisions and automated reporting for precision oncology*. Nature Cancer. 2022;3:251–261. [DOI: 10.1038/s43018-022-00332-x](https://doi.org/10.1038/s43018-022-00332-x). PMID 35221333.
3. Perera-Bel J et al. *From somatic variants towards precision oncology: Evidence-driven reporting of treatment options in molecular tumor boards*. Genome Medicine. 2018;10:18. [DOI: 10.1186/s13073-018-0529-2](https://doi.org/10.1186/s13073-018-0529-2). PMID 29544535; PMCID PMC5856211.
4. Griffith M et al. *CIViC is a community knowledgebase for expert crowdsourcing the clinical interpretation of variants in cancer*. Nature Genetics. 2017;49:170–174. [DOI: 10.1038/ng.3774](https://doi.org/10.1038/ng.3774). PMID 28138153; PMCID PMC5367263.
5. Chakravarty D et al. *OncoKB: A Precision Oncology Knowledge Base*. JCO Precision Oncology. 2017. [DOI: 10.1200/PO.17.00011](https://doi.org/10.1200/PO.17.00011). PMID 28890946; PMCID PMC5586540.
6. Hübschmann D et al. *The Knowledge Connector decision support system for multiomics-based precision oncology*. Nature Communications. 2026;17:742. [DOI: 10.1038/s41467-026-68333-3](https://doi.org/10.1038/s41467-026-68333-3).
7. Berman T et al. *Retrieval Augmented Therapy Suggestion for Molecular Tumor Boards: Algorithmic Development and Validation Study*. Journal of Medical Internet Research. 2025;27:e64364. [DOI: 10.2196/64364](https://doi.org/10.2196/64364). PMID 40053768; PMCID PMC11923455.
