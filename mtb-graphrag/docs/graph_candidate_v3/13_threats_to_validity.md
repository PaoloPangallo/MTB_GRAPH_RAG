# 13 — Minacce alla validità

## Validità di costrutto

**«Fedeltà semantica» è definita rispetto ai metadati, non al testo.**
`source_alignment_status` riflette `evidence_direction`, un campo di annotazione
CIViC. Se quell'annotazione fosse sbagliata rispetto al paper, v3 la
riprodurrebbe fedelmente e sarebbe comunque scorretta. v3 misura la fedeltà alla
**sorgente**, non alla letteratura.

**Il parsing delle alterazioni presuppone che il nome del profilo sia la verità.**
Il nome è una stringa curata a mano. La validazione incrociata con gli archi
(197/197 profili concordanti) mostra che nome e struttura del grafo sono
coerenti, ma entrambi derivano dalla stessa curazione: non sono due osservazioni
indipendenti.

**`MULTI_COMPONENT_UNRESOLVED` accorpa casi diversi.** Combinazioni vere,
alternative confrontate e sequenze finiscono nello stesso stato. È una perdita di
risoluzione deliberata, preferibile all'alternativa (inventare la distinzione),
ma resta una perdita: 572 candidate sono meno informative di quanto potrebbero
essere con una sorgente migliore.

## Validità interna

**La regola delle parentesi è una scelta, non un dato.** «Gruppo logico se e solo
se contiene un operatore» separa correttamente tutti i 310 casi osservati, ma è
una regola che ho definito osservando il corpus. Un'espressione futura come
`(BRAF V600E) AND (KRAS G12D)` — parentesi di raggruppamento senza operatore
interno — verrebbe trattata come parte del termine. Il corpus non ne contiene, ma
la regola non è universale.

**Il conteggio dei termini è validato contro la stessa curazione.** Che
`name-term count == linked-variant count` su 197/197 profili è forte, ma verifica
la coerenza interna dell'export, non la sua correttezza.

**La riderivazione indipendente condivide le funzioni di identità.** `edge_id` e
`payload_hash` sono riprodotti, non riprogettati. Un errore di contenuto cambia
comunque il digest, ma un errore nella funzione di identità stessa non sarebbe
rilevabile.

**Il materializzatore v3 e il verificatore condividono l'audit della sorgente.**
Entrambi discendono dallo stesso `01_source_semantics_audit.md`. Se l'audit avesse
frainteso un campo, l'errore si propagherebbe a entrambi senza essere rilevato. La
mitigazione è che l'audit è tracciato riga per riga sui dati e riproducibile.

## Validità esterna

**Un solo export, una sola versione.** Le quote misurate (873 `DOES_NOT_SUPPORT`,
1 010 alterazioni composte, 572 regimi irrisolti) sono proprietà di questo corpus.

**La grammatica implementa solo gli operatori osservati.** Un export con
`,` come separatore logico, o con annidamento più profondo, richiederebbe
un'estensione — con il rischio di reintrodurre l'ambiguità che la regola delle
parentesi risolve.

**`COMBINATION_CONFIRMED` non è mai stato esercitato.** Il ramo esiste, è coperto
da un test sintetico, ma non da dati reali: nessuno lo ha mai attraversato.
Lo stesso vale per `CONTRADICTS_ASSERTION` e per ogni `component_role` diverso da
`UNKNOWN`.

## Validità di conclusione

**Le otto metriche a zero sono verificate, non assunte** — ma verificano
l'assenza di una classe di errore *come definita dal codice di misura*. Per
esempio `compound_operator_lost` conta gli operatori presenti nel raw e assenti
dall'AST: non rileverebbe un operatore correttamente presente ma associato agli
operandi sbagliati. Il test sull'annidamento (`AND(T, OR(T,T))`) copre quel caso
sui dati reali, ma per costruzione dell'esempio, non esaustivamente.

**«v3 è semanticamente più fedele» è dimostrato per i tre difetti misurati**, non
in generale. v3 potrebbe avere perdite semantiche che nessuno ha ancora
individuato — esattamente come v2 aveva le sue prima dell'audit RQ1.

**Il campione manuale non è annotato.** La fedeltà semantica non ha ancora una
verifica umana indipendente. Le colonne del revisore sono vuote per costruzione, e
un test lo verifica.

**Il conteggio inferiore di candidate non è di per sé un miglioramento.** È
esplicitamente registrato nel confronto shadow, perché la tentazione di leggere
−722 come «meno rumore» è reale e sarebbe un errore: la riduzione è giustificata
solo dal fatto che i 722 path fusi descrivevano una relazione non separabile.

## Riepilogo

| Minaccia | Gravità | Mitigazione |
|---|---|---|
| Fedeltà ai metadati scambiata per fedeltà alla letteratura | **Alta** | Dichiarata; `SOURCE_ALIGNED` documentato come stato del metadato |
| Regola delle parentesi non universale | Media | Copre 310/310 casi; documentata come regola, non come legge |
| Nome del profilo e archi non indipendenti | Media | Dichiarata |
| Rami di enum mai esercitati | Bassa | Elencati esplicitamente nel manifest e nello schema |
| Campione manuale non annotato | Media | 70 record pronti |
| −722 candidate letto come miglioramento | Media | Nota esplicita nel confronto shadow |
