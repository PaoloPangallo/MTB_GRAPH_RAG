# Architecture Explorer GCA4

Aprire `/architecture` dopo `npm run dev` dalla cartella frontend. La console
principale include il collegamento **Esplora architettura**.

## Esecuzione reale

`/architecture` apre il testo del caso. **Esegui la pipeline** invia una richiesta
reale a `POST /api/v1/research/pipeline/runs`: il backend usa il provider e le fonti
configurati. Nessuna run parte per effetto dell'apertura della pagina.

La run resta nell'URL (`?run=<id>`). L'Explorer riusa `useRunStream`, con snapshot,
SSE e recupero eventi già presenti nella console. **Segui esecuzione** segue lo
stage corrente; selezionando uno stage si passa all'ispezione manuale. Input,
output, eventi e chiamate vengono caricati dall'endpoint pubblico dello stage.
La proiezione può omettere/redigere campi: la UI non ricostruisce payload assenti.
I controlli semantici interni alla validazione sono visibili solo nei dati
registrati, senza presumere che una chiamata sia avvenuta.

Il collegamento dalla console conserva la run selezionata. A fine esecuzione il
dossier è ispezionabile nello stage corrispondente e nella console canonica.
Run fallite, parziali e output mancanti restano espliciti. Leggere una run
archiviata non riesegue il modello. Il trasporto è compatto per il progresso;
i dettagli completi pubblici sono caricati solo per lo stage selezionato.

## Demo separata

La simulazione offline è disponibile su `/architecture?mode=demo`.

## Come leggere la demo

La vista demo mostra **solo il percorso dello scenario selezionato**.
Ogni nodo è una tappa della sequenza dimostrativa; le frecce in questa vista
indicano l’ordine degli eventi. I testi sono HTML e mantengono dimensioni
leggibili quando il diagramma cambia layout.

Il pannello del passaggio spiega l’operazione, ciò che entra e ciò che esce.
Selezionando una tappa si raggiunge quell’evento e si mette in pausa la
riproduzione. Il dossier finale compare soltanto al passaggio di presentazione,
senza anticipare un risultato ancora da raggiungere.

**Mappa completa** mostra tutti i componenti e i collegamenti condizionali.
Selezionare un componente per leggerne responsabilità, input/output e condizioni
dei rami. Le connessioni che bypassano più componenti passano nei margini del
diagramma. L’ispezione è distinta dallo stato della simulazione.

La riproduzione procede ogni 2,8 secondi alla velocità 1×. Sono disponibili
pausa, precedente, successivo, reset, velocità e navigazione diretta tramite
slider. Pan e zoom sono locali al diagramma. Il canvas segue il nodo corrente
quando questo esce dalla parte visibile. Su mobile il dettaglio precede il
diagramma e il canvas ha un’altezza limitata, evitando una lunga colonna di
nodi prima della spiegazione. `prefers-reduced-motion` disattiva flussi animati
e scorrimento automatico graduale.

## Scenari e confini scientifici

Gli scenari sintetici illustrano citazione verificabile, citazione incompatibile,
semantic alignment simulato, percorsi distinti EVIDENCE_STATEMENT/TRIAL/KG_ONLY
e fallback BM25_STRUCTURE con run parziale e accounting FAIL.

La demo conserva il modello canonico in `src/architecture/model.ts`; i testi
di presentazione sono separati in `presentation.ts`. Le fixture sono DEMO,
non risultati clinici o nuovi output di un LLM. La pagina non fa richieste al
backend, a provider, a font esterni o a modelli.

EVIDENCE_DRUG raggiunge la verifica semantica solo dopo autenticazione e
structural PASS. EVIDENCE_STATEMENT usa la propria policy deterministica.
TRIAL non implica efficacia o eleggibilità; KG_ONLY non attraversa il Reader.
L’accounting è distinto dal supporto scientifico e un FAIL impedisce la
pubblicazione come dossier completo.

## Verifiche

```sh
node node_modules/vitest/vitest.mjs run src/architecture/ArchitectureExplorer.test.tsx src/architecture/model.test.ts src/App.test.tsx
npm run typecheck
npm run build
```

I test controllano navigazione, pausa, ispezione dopo l’avvio, visibilità delle
condizioni, separazione delle famiglie e comparsa del dossier al momento corretto.
Non costituiscono una validazione scientifica delle verifiche simulate.

Possibili estensioni future: adattatore per eventi backend registrati,
esportazione della mappa e modalità di presentazione. Nessuna di queste è
collegata a run cliniche nella versione attuale.
