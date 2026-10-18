---
name: MTB — System design
description: Estensione dell'atlante orale per il relatore, con identita sobria teal/inchiostro e spiegazioni in linguaggio comune. Il percorso presenta 18 passaggi numerati da 1 a 18: numeri di presentazione, distinti dagli identificativi interni degli stage.

Tre esempi accompagnano la lettura: melanoma e BRAF V600K, studio sul sangue e collegamento diagnostico. Il caso e sintetico; associazioni e contenuti provengono dal Knowledge Graph e dal dossier dell'analisi archiviata del 15 ottobre 2026. Scegliere un esempio non avvia una nuova analisi.

## Colors

I colori del frontmatter riproducono le custom properties CSS. Carta bianca e superficie tenue sostengono testo inchiostro, testo secondario e divisori. Teal segnala link, navigazione selezionata e pulsanti degli esempi selezionati. Viola distingue i controlli; ocra distingue modello e componenti misti. Etichette testuali accompagnano i colori.

`model-soft` compare nella legenda; `limit` è dichiarato ma non utilizzato da altre regole del foglio attuale. I nodi di mappa hanno anche fondi locali: modello `#fdf8ed`, controllo `#f7f4fb`, misto `#f8f3e8`. Il focus usa un accento blu distinto.

## Typography

Arial/Helvetica è lo stack locale, senza font remoti. Titoli h2: 23px/1.25; h3: 17px/1.35. Le intestazioni dei dettagli e dei diagrammi scendono a 19 e 18px; navigazione e controlli usano circa 11–13px. Il testo introduttivo è 16px/1.75, con paragrafi generalmente limitati a 74ch. Codice ed estratti usano Consolas/Courier New; gli estratti sono 12.5px/1.65 con ritorno a capo. La sola marca «m» usa Georgia.

## Layout

Contenitore massimo 1800px; barra superiore sticky di 78px e griglia con indice laterale sticky di 258px. Il contenuto ha padding 40px 44px 24px. Mappa a corsie, colonne affiancate per panoramica e contratti, diagrammi in area scorribile con altezza massima 520px.

- Da 1500px: padding principale 46px 60px 24px e diagrammi più ariosi.
- Fino a 1050px: indice 230px, padding principale 32px 27px 24px, dettagli su una colonna; scompare il testo visibile dell'etichetta del selettore esempio, che resta nel DOM.
- Fino a 760px: barra 68px, indice fisso di 290px aperto dal pulsante Fasi, contenuto con padding 30px 20px 24px; mappa su due nodi per riga e panoramica su una colonna. Il pulsante stampa è nascosto. Il diagramma conserva una larghezza minima di 650px e richiede scorrimento orizzontale.
- Fino a 480px: dicitura Come funziona e separatore accanto a MTB vengono nascosti per riservare spazio ai controlli; il selettore esempio ha larghezza massima mobile di 145px (250px su desktop).

Stampa: A4 verticale con margini di 15mm, copertina e inizio pagina per ogni fase. Barra e interfaccia interattiva vengono sostituite da un documento completo con diagrammi, contratti, controlli, limiti, decisioni, esempio selezionato e provenienza finale.

## Elevation & Depth

Sistema piatto: bordi sottili, fondi tonali e spazio definiscono la gerarchia, senza ombre. Barra e indice mobile si sovrappongono tramite posizionamento e z-index.

## Shapes

Pannelli principali con raggio 12px; nodi, ispettore e blocchi sorgente con 8px; pulsanti e campi con 7px; link dell'indice con 6px. Pulsanti con bordo sottile e padding 8px 12px, altezza minima 36px. Non è una scala universale di target tattili: alcuni controlli del diagramma sono più compatti.

## Components

**Vista principale corrente.** Sei macrofasi navigabili con grafi specifici: comprensione del caso, recupero GCA, analisi delle fonti, verifiche, dossier e presentazione. Diciotto approfondimenti richiudibili. Nomi scientifici GCA, Case Parser, BM25 strutturale, MedCPT, RRF e Reader conservati. I tre percorsi sono sempre selezionabili; l’esempio BRAF conserva ingresso, trasformazione e uscita. Nessuna data, identificativo di esecuzione o metadato operativo nella vista del relatore. Tabella esplicita per default e opzioni. I diagrammi hanno orientamento verticale, testo più grande e nessun limite artificiale di altezza; sullo schermo stretto scorrono orizzontalmente. Ogni macrofigura esporta SVG, PDF vettoriale e DOT anche dal documento offline. La stampa antepone le sei macrofasi agli approfondimenti. Le descrizioni storiche seguenti descrivono i componenti conservati della revisione precedente, non la nuova gerarchia.

**Lettura e navigazione.** Panoramica con tre pulsanti di scelta dell'esempio, nota su associazioni reali e caso sintetico, mappa e riepilogo del caso. Ricerca per numero, nome, sintesi e componente. Quattro schede: Come funziona, Che cosa entra ed esce, Come si controlla, Esempio e fonte. Hash URL conserva fase, esempio e pannello; cambiare fase apre la sintesi. Profili tecnici, identificativi degli stage, sorgenti e hash non sono esposti.

**Esempi e provenienza.** Pannello con fondo #f2f7f4, bordo #c9dbd3, raggio 12px e padding 23px 25px; titolo 19px e testo 14px/1.75. La scheda Esempio e fonte mostra percorso, fatti, eventuale estratto originale, limiti e provenienza; link esterni in nuova scheda con noopener noreferrer. Estratti in Georgia 17px/1.7. L'associazione diagnostica senza pubblicazione non simula letture o citazioni; lo studio di registro resta distinto da efficacia ed eleggibilita individuale.

**Diagramma.** 19 SVG correnti: 18 passaggi e una variante solo-grafo per l'esempio diagnostico nei cinque passaggi documentali. Ispettore del componente, zoom 70%-200%, pulsante 100% per ripristinare la scala. Scarica figura esporta SVG mediante Blob locale; nessun download DOT esposto.

**Stampa aggiornata.** Copertina, tutti i 18 passaggi con esempio selezionato, diagrammi, ingressi/uscite, controlli, limiti e decisioni; sezione finale con dettaglio e provenienza dell'esempio.

**Accessibilità implementata.** Link per saltare al contenuto; landmark e tabelle con intestazioni; stato corrente dell'indice; tablist/tabpanel con selezione e tabindex mobili. Frecce, Home ed End cambiano scheda; Invio e Spazio attivano i nodi SVG. Focus visibile di 3px con offset 4px; sui nodi SVG cambia il tratto. Annunci polite comunicano selezioni e download. Aprire il menu porta il focus alla ricerca; Escape lo chiude e restituisce il focus al pulsante. La navigazione tra fasi porta il focus al contenuto. Le preferenze di movimento ridotto disattivano transizioni e animazioni; quelle ordinarie dei nodi durano .15s.

**Locale e offline.** `System_design_architettura.html` incorpora stile, dati, SVG, DOT, estratti e script; può essere aperto da solo senza server o dipendenze remote. `index.html` richiede i file adiacenti. JavaScript è necessario alla navigazione e alla preparazione della stampa; il fallback noscript lo dichiara.

**Limiti della verifica.** Il passaggio di verifica comunica 15 test superati e copertura delle 216 combinazioni: 18 fasi, tre esempi, quattro schede. Risultati forniti dal responsabile della verifica, senza ulteriore esecuzione del documenter. Browser non disponibile: nessuna verifica visiva, di focus SVG nativo, download o paginazione reale. Gli esempi riprendono un'analisi archiviata; nessuna nuova run LIVE.

## Do's and Don'ts

Aggiornamento del 17 ottobre 2026: panoramica con sei componenti logici e dati trasmessi, preparazione a monte e coordinamento trasversale. Tre percorsi espliciti: pubblicazione, registro, solo grafo. Ogni fase e la stampa includono ingresso, trasformazione e risultato progressivo. `journey.js` conserva parafrasi didattiche; i risultati dichiarati provengono dall’archivio. Diagrammi specifici mostrano confluenza nel dossier, composizione e verifica finale. Le etichette distinguono codice deterministico, modello linguistico e controlli misti. Browser non disponibile nella sessione: verifica DOM e immagini dei diagrammi Graphviz.

- **Do** conservare l'identità teal/inchiostro e Arial dell'atlante e la progressione dalla sintesi ai dettagli.
- **Do** accompagnare distinzioni cromatiche con etichette e mantenere raggiungibili controlli e nodi da tastiera.
- **Do** rigenerare l'HTML autonomo quando cambiano le sorgenti separate, seguendo il README.
- **Don't** trasformare la mappa logica in una rappresentazione di microservizi o capacità non implementate.
- **Don't** presentare scelte degli esempi o test DOM come esecuzioni LIVE o validazione visiva del browser.

Questo passaggio documentale è limitato a `DESIGN.md`; non introduce sidecar, token sintetici o artefatti di tooling.
