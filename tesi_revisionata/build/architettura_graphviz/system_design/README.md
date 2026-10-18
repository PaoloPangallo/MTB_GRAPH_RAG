# Architettura per il relatore

Apri [Architettura_per_il_relatore.html](Architettura_per_il_relatore.html): è un documento autonomo, utilizzabile offline senza installazioni. `System_design_architettura.html` contiene la stessa versione aggiornata. La precedente versione tecnica è conservata localmente in `System_design_versione_tecnica.html`.

La vista principale introduce **sei macrofasi navigabili**: comprensione del caso, recupero GCA, analisi delle fonti, verifiche, dossier e presentazione. Ognuna ha un diagramma Graphviz specifico; una settima figura spiega RRF con un esempio numerico. I **18 passaggi** precedenti rimangono approfondimenti richiudibili. I 16 passaggi operativi del codice sono affiancati dalla preparazione delle informazioni e dal coordinamento trasversale: la numerazione espositiva non aggiunge fasi al programma.

Anche i diciotto approfondimenti hanno diagrammi specifici, senza lo schema generico “controllare il passaggio / segnalare un limite” e senza etichette di categoria ripetute nei nodi. La lettura parte dal componente, dalle sue operazioni e dai dati scambiati; l’esempio segue come applicazione concreta. Entity Resolution mostra concetto di malattia e contesto, gene–variante e intervento non risolto; l’esempio del gate distingue esito operativo e supporto documentale.

Ogni macrofase mostra un esempio incrementale: **Da dove arriviamo → Che cosa cambia → Che cosa portiamo avanti**. L’uscita ricompare come ingresso della successiva. Le trasformazioni sono parafrasi didattiche basate sul codice; i risultati dichiarati provengono dall’archivio. La stampa comprende sei macrofasi, RRF e gli approfondimenti. [verifica/MACROFASI_RISCONTRO.md](verifica/MACROFASI_RISCONTRO.md) documenta confronto con codice, differenze rispetto alla versione precedente e limiti della verifica. Date, identificativi delle esecuzioni e metadati operativi non sono mostrati al relatore.

Il selettore segue tre esempi attraverso l'intero percorso:

- **Pubblicazione:** BRAF V600K e lo studio associato alla pubblicazione 28891408. L'esempio distingue il contesto dello studio dal caso sintetico; una citazione autentica non equivale a sostegno della relazione cercata.
- **Studio registrato:** BRAF e NCT02279004, uno studio sulla genotipizzazione del plasma. Le informazioni archiviate non dimostrano efficacia né eleggibilità individuale e non attestano lo stato attuale del reclutamento.
- **Collegamento diagnostico:** FoundationOne CDx e BRAF. Questo record conserva la provenienza nel Knowledge Graph senza inventare una pubblicazione o una lettura documentale.

Le associazioni provengono dal Knowledge Graph effettivamente caricato dal progetto. Gli esiti provengono dall'esecuzione archiviata del 15 ottobre 2026, su un **caso sintetico, non un paziente reale**. Non sono state avviate nuove analisi o chiamate ai modelli. La pagina separa dati presenti nel grafo, osservazioni dei documenti ed esiti dei controlli.

## Lessico per l'esposizione

| Nome nel codice o nella versione precedente | Nome mostrato al relatore |
| --- | --- |
| GCA | GCA, spiegate come associazioni candidate dal grafo |
| CleanGraphData | Knowledge Graph |
| focused-v1 | Profilo opzionale, distinto dal percorso predefinito |
| SourceUnit | Passaggio della fonte |
| Reader | Reader, spiegato come lettura della fonte |
| BM25, MedCPT, RRF | Nomi conservati e funzionamento spiegato |
| matching | Ricerca delle associazioni pertinenti |
| ranking | Ordinamento per pertinenza |
| dossier | Rapporto finale |

La tabella delle configurazioni distingue i default del codice dalle opzioni. Il registro senza Reader generativo è condizionato a focused-v1; non viene attribuito al percorso predefinito. Il confronto semantico aggiuntivo è condizionato alla famiglia EVIDENCE_DRUG, all’osservazione ammessa e alla struttura superata. I nomi scientificamente importanti restano visibili; identificativi interni e impronte rimangono nei materiali di verifica.

## Corrispondenza con il codice e con i dati

[verifica/sources.json](verifica/sources.json) conserva 62 riferimenti a 38 file sorgente, con posizione e impronta del contenuto. Il generatore confronta l'ordine dei 16 passaggi con il contratto del backend. [verifica/esempi.json](verifica/esempi.json) conserva i cinque record originali del Knowledge Graph, le impronte dei file e gli esiti dell'esecuzione archiviata. Il caso sintetico e l'assenza di nuove esecuzioni sono registrati esplicitamente.

La verifica riguarda il checkout locale del 17 ottobre 2026. Backend, manoscritto e PDF della tesi non sono stati modificati. La documentazione è una sintesi del codice, non una dichiarazione di capacità ulteriori.

## Uso e verifiche

### Audit del corpus GCA

`Audit_GCA_per_il_relatore.html` è una pagina autonoma dedicata al censimento di tutte le associazioni candidate del runtime, collegata dalle due edizioni dell'architettura. Mostra anatomia del record, famiglie, percorsi delle fonti, disponibilità nello snapshot documentale, integrità, copertura, identità, contesto, concentrazione, esempi e confronto storico fra versioni. Non effettua una nuova verifica clinica o un recupero di documenti.

`python build-gca-audit.py` verifica l'impronta del corpus richiesta dal loader, ricalcola le statistiche e confronta i conteggi con i report congelati. Produce HTML con CSS/SVG incorporati, `verifica/gca-audit.json`, `verifica/gca-audit-tabelle.csv` e lo schema DOT/SVG/PDF in `figure/audit-gca/`. Il comando è incluso anche in `export-vectors.ps1`.

Le 5.002 ricorrenze di chiave semantica sono distinte dai duplicati di identificativo; i quattro riferimenti PMID malformati corrispondono a due valori DOI distinti. Le percentuali dichiarano il denominatore. `python tests/test_gca_audit.py` verifica classificazione, conteggio delle ricorrenze e corrispondenza dell'intero censimento; `node tests/audit.test.cjs` controlla la pagina offline e i collegamenti.

### Audit delle pubblicazioni e degli studi NCT

La sezione Fonti dell'audit GCA apre `Audit_paper_NCT_per_il_relatore.html`, con due approfondimenti dedicati. Per le pubblicazioni presenta identificativi, collegamenti alle GCA, metadati bibliografici, abstract e corpo XML PMC. Per gli studi presenta metadati del grafo e contenuti della cache: stato, tipo, fasi, condizioni, interventi, bracci, criteri e flag dei risultati depositati. Le tabelle dichiarano il denominatore e lo snapshot di riferimento.

`document_audit.py`, richiamato da `build-gca-audit.py`, segue la configurazione della cache del runtime (`RESEARCH_DOCUMENT_CACHE_PATH`, poi `RESEARCH_PIPELINE_CACHE_ROOT`, infine la radice dati). La lettura usa l'ultima voce del manifest per ogni `document_id`, confronta identità e impronte e conserva le impronte dei file esaminati. Gli XML PMC comprendono il contenitore OAI-PMH e i tipi di identificatore `pmc` e `pmcid`.

I risultati completi sono in `verifica/fonti-audit.json`; `paper-audit-inventario.csv` e `nct-audit-inventario.csv` conservano una riga per identificativo con i collegamenti ai record GCA. I 2.222 PMID numerici e i 4.136 NCT sono censiti sull'intero corpus; le distribuzioni dei contenuti usano i sottoinsiemi di metadati o payload con identità conforme. Gli stati degli studi appartengono allo snapshot letto; il flag `hasResults` indica il deposito di risultati nel registro. La valutazione del caso resta nel percorso del dossier.

Verifiche: `python tests/test_document_audit.py` copre identità, OAI-PMH, impronte, versioni del manifest e confini dei percorsi; `python tests/test_document_output.py` riconcilia inventari, conteggi e collegamenti con il censimento GCA; `node tests/audit.test.cjs` controlla anche la nuova pagina e la navigazione.

### Audit delle source unit

`Audit_source_unit_per_il_relatore.html` presenta la struttura delle unità, i tipi di contenuto, le identità delle occorrenze, i locatori, le lunghezze, i parser e il ruolo dei passaggi nella selezione e nella citazione. Il pulsante `Audit source unit` è accanto agli altri audit nella barra dell'architettura.

`sourceunit_audit.py` ricostruisce le unità attraverso `ReadOnlyDocumentCache.source_units_for_record`, usando i payload collegati al corpus che hanno superato i controlli di identità e impronta dell'audit delle fonti. L'indice storico di 3.402 locatori su 40 documenti è descritto separatamente. Gli offset delle frasi full text sono verificati nel paragrafo di origine; quelli PubMed nell'abstract completo. L'inventario conserva anche le ripetizioni di contenuto nelle diverse occorrenze.

La ricostruzione corrente comprende 255.051 unità da 3.920 documenti, suddivise in 16 tipi. `verifica/sourceunit-audit.json` conserva statistiche, esempi e impronte; `sourceunit-documenti.csv` contiene una riga per documento; `sourceunit-inventario.csv.gz` contiene una riga per unità, con impronta del testo e coordinate. Il testo integrale resta nella cache documentale. La generazione è inclusa in `python build-gca-audit.py`; `python sourceunit_audit.py` permette di eseguire il solo censimento delle unità a partire dall'audit delle fonti già aggiornato.

I test `python tests/test_sourceunit_audit.py` verificano identità per occorrenza, celle ripetute, indici pari a zero, offset locali, totali e inventario compresso. `node tests/audit.test.cjs` verifica anche la pagina e il nuovo pulsante nelle due edizioni dell'architettura.

Ricerca laterale, navigazione da tastiera, zoom ed esportazione SVG/PDF/DOT accompagnano le macrofasi. I PDF sono incorporati nel documento autonomo: il download funziona anche senza i file adiacenti. Il collegamento conserva macrofase o approfondimento, esempio e scheda. Il cambio percorso conserva il focus da tastiera.

I test coprono navigazione, dati, contenuto, provenienza, comportamento DOM, sei macrofasi con tre percorsi, RRF e asset offline, oltre alle **216 combinazioni** di 18 approfondimenti, tre esempi e quattro schede. I PDF sono stati renderizzati per ispezione e controllati con pypdf: testo selezionabile, nessuna immagine raster. Il browser integrato non era disponibile: i test DOM non verificano la resa visiva della pagina, i download nativi o la paginazione reale.

## Rigenerare

### Edizioni e percorsi coerenti

`Architettura_per_il_relatore_breve.html` presenta soltanto le sei macrofasi con l'esempio trasversale selezionato. I tre `Relatore_breve_*.pdf` in `output/pdf/architettura/` contengono sei pagine A4 ciascuno, con testo selezionabile e schemi vettoriali. La pagina completa conserva i diciotto approfondimenti e offre stampa breve, stampa completa e download del PDF breve corrispondente alla fonte scelta.

`path-views.js` definisce le varianti condivise da schermo, stampa ed esportazioni; `path-build.cjs` genera 58 varianti DOT in `figure/percorsi/`. `build-brief.py` compone i PDF senza rasterizzare gli schemi. `export-vectors.ps1` rigenera tutte le varianti, i PDF brevi e i tre HTML autonomi nell'ordine richiesto. Non usare il solo `--assemble` dopo una modifica dei grafi: occorre prima rigenerare i vettori.

L'estrazione controlla esplicitamente che il registro documentato abbia fatti strutturati, zero chiamate al modello, gate ambiguo ed eleggibilità non valutata; il record solo grafo non deve avere chiamate documentali né un esito del gate. Questi riscontri non sono attribuiti automaticamente al percorso predefinito. Le classifiche RRF restano un calcolo didattico, separato dai risultati archiviati. `tests/paths.test.cjs` verifica figure alternative, approfondimenti, terminologia e le due forme della versione breve.

`macro-data.js` conserva contenuti, trasformazioni BRAF e grafi delle macrofasi; `macro-ui.js` ne gestisce la lettura. `macro-build.cjs` scrive i DOT e verifica riferimenti al backend. `data.js` e `journey.js` conservano gli approfondimenti; `public-data.js`, `assets.js` e i due HTML autonomi sono generati. I sorgenti DOT e gli SVG/PDF sono in `figure/macrofasi/`; la raccolta PDF e i singoli schemi sono anche in `output/pdf/architettura/` alla radice del progetto.

`detail-lessons.cjs` conserva i meccanismi e i grafi dei diciotto approfondimenti. `build.cjs` li applica ai dati pubblici. DOT, SVG e PDF degli approfondimenti sono in `figure/`; la raccolta vettoriale è `output/pdf/architettura/Approfondimenti_architettura.pdf`. Entrambi i livelli esportano SVG, PDF e DOT dalla pagina offline. `extract-examples.cjs` verifica anche le identità mostrate nell’Entity Resolution e l’esito operativo del gate; i riscontri rimangono in `verifica/esempi.json`.

Dalla cartella del documento, con Node.js e Graphviz disponibili:

```powershell
node extract-examples.cjs
node build.cjs
Get-ChildItem figure -Filter *.dot | ForEach-Object {
  dot -Tsvg $_.FullName -o ([IO.Path]::ChangeExtension($_.FullName, '.svg'))
}
./export-vectors.ps1 -Graphviz 'C:\Program Files\Graphviz\bin\dot.exe'
node tests/navigation.test.cjs
node tests/document.test.cjs
node tests/audience.test.cjs
node tests/journey.test.cjs
node tests/macros.test.cjs
node tests/explanation.test.cjs
```

Gli strumenti di rigenerazione leggono il backend e i dati nelle posizioni del progetto originale. I test DOM usano `jsdom` già presente nel frontend. Il documento autonomo consegnato non richiede il repository né tali strumenti.
