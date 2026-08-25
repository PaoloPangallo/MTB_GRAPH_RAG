# Sintesi dell’architettura per il relatore

## Il problema

Ho analizzato lavori sui Molecular Tumor Board e sulle knowledge base oncologiche. La letteratura mostra due esigenze complementari: organizzare conoscenza molecolare eterogenea e rendere le associazioni verificabili in report utilizzabili durante una discussione MTB. Una relazione presente in una base di conoscenza può infatti avere significati e provenance diversi: può derivare da un paper, collegarsi a un trial clinico oppure essere disponibile nel grafo senza una fonte primaria direttamente utilizzabile.

Il rischio è presentare tutte queste associazioni come se avessero lo stesso valore documentale, oppure affidare a un modello linguistico il compito di completare riferimenti e interpretazioni mancanti. Il sistema è stato progettato per evitare entrambe le semplificazioni.

## Cosa è stato progettato

La pipeline riceve un testo clinico e produce un dossier MTB strutturato e tracciabile:

1. Gemma estrae dal testo un `CaseContext` con malattia, biomarcatori, varianti, terapie menzionate e obiettivo della domanda.
2. Controlli deterministici verificano schema, riscontro letterale e sufficienza del contesto. Un caso insufficiente o ambiguo si ferma prima del retrieval.
3. Il sistema cerca relazioni pertinenti nelle 46.864 Graph Candidate Assertions già materializzate dal Knowledge Graph oncologico.
4. La provenance divide le candidate in tre rami distinti.
5. Un builder deterministico produce il dossier canonico, senza Writer narrativo.

Se il retrieval non trova relazioni pertinenti, il sistema restituisce un dossier vuoto con stato `NO_RELEVANT_KG_EVIDENCE`. L’assenza di evidenza non viene trattata come errore e non attiva generazione testuale compensativa.

## Perché un Knowledge Graph

Il Knowledge Graph non viene usato soltanto come indice per recuperare testi. Propone associazioni già strutturate tra varianti, geni, malattie, farmaci, evidenze e trial; preserva il tipo di relazione; conserva la provenance grafica; fornisce PMID o NCT quando disponibili.

Il grafo non decide una terapia e una sua relazione non viene considerata automaticamente vera a livello documentale. Stabilisce invece quali associazioni devono essere considerate e quale strategia di verifica è applicabile.

## I tre rami

**Paper evidence.** Se la GCA contiene un PMID, il sistema torna alla fonte associata. Preferisce il full text PMC quando disponibile e parsabile, altrimenti usa l’abstract PubMed. Il documento viene diviso in SourceUnit identificabili; un selector deterministico riduce il contesto; Gemma restituisce una citazione letterale e descrive ciò che osserva. Un validatore controlla che la quote esista davvero nella SourceUnit. Infine una funzione deterministica confronta disease, gene, variante, farmaco, direzione ed evidence type richiesti dalla relazione. Per relazioni diagnostiche o prognostiche non impone campi terapeutici non applicabili.

**Clinical trial.** Se la GCA contiene un NCT, il sistema recupera il record strutturato di ClinicalTrials.gov: titolo, stato, fase, condizioni e interventi. Non usa il Paper Reader, non estrae quote e non interpreta il trial come prova di efficacia o eleggibilità del paziente.

**KG-only.** Se la GCA non contiene PMID o NCT, il sistema preserva soggetto, relazione, oggetto, database sorgente e lineage grafica. Dichiara esplicitamente `document_provenance=NOT_AVAILABLE`. Non cerca un paper alternativo e non inventa una fonte.

## Ruolo limitato di Gemma

Il core usa Gemma in due ruoli circoscritti:

- Case Parser: trasforma il testo clinico in dati strutturati senza aggiungere fatti esterni.
- Paper Reader: legge soltanto SourceUnit selezionate e restituisce osservazioni strutturate e una quote letterale.

Retrieval, classificazione della provenance, quote validation, support verification e dossier sono deterministici. Writer e Narrative Verifier possono rimanere nel repository per compatibilità o sperimentazione, ma non appartengono al normale percorso canonico.

## Cosa produce e quali controlli applica

Il dossier primario contiene riepilogo del caso, riepilogo del retrieval, paper verificati, trial, relazioni KG-only, limitations e sintesi della provenance. Ogni paper può essere seguito dalla candidate alla GCA, dal PMID al documento, dalla SourceUnit alla quote e dalla quote all’esito. Trial e KG-only mantengono catene analoghe appropriate alla loro fonte.

Un esempio di controllo della specificità è il caso mCRC, KRAS G12D e panitumumab. La fonte associata documenta resistenza a panitumumab per mutazioni KRAS, ma non conferma specificamente G12D. Il dossier restituisce quindi `PARTIAL_SUPPORT`; il sistema non completa automaticamente la specificità mancante.

## Cosa non pretende di fare

Il sistema non prescrive terapie, non sostituisce il giudizio clinico, non valida la verità clinica assoluta del KG, non considera la presenza di un trial prova di efficacia e non valuta automaticamente l’eleggibilità del paziente. Verifica la corrispondenza tra una relazione candidata e la fonte ad essa associata, nei limiti del documento disponibile.

## Valutabilità successiva

L’architettura espone campi stabili per una valutazione successiva: validità della quote, supporto per campo ed esito complessivo nei paper; correttezza di NCT e metadati senza overclaim nei trial; conservazione della provenance e assenza di fonti inventate nelle KG-only; completezza della tracciabilità per tutte le entry. Questa valutazione è separata dal consolidamento architetturale.
