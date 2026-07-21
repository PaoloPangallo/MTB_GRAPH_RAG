# MTB-Evidence pilot v1 — note di annotazione

## Stato

Questi quattro casi costituiscono una **prima annotazione strutturata**, non ancora
una ground truth congelata. Ogni caso richiede una seconda revisione indipendente.
Il caso RMI2 richiede inoltre il salvataggio della query vuota sullo snapshot
Neo4j congelato.

## Casi

### K1 — FGFR2 fusion/rearrangement, intrahepatic cholangiocarcinoma

La domanda è intenzionalmente definita su malattia avanzata/non resecabile o
metastatica, già trattata e senza precedente esposizione a FGFR-inibitori. Le
claim attese riguardano pemigatinib e futibatinib, con popolazione e linea
esplicite. Non è ammessa una formulazione generica del tipo “FGFR2 fusion è
sensibile a qualunque FGFR-inibitore”.

### A2 — ALK G1202R

Il caso specifica una **mutazione singola** G1202R dopo progressione a un
ALK-TKI di seconda generazione. La pipeline deve riconoscere la resistenza,
recuperare l'evidenza su lorlatinib e attivare la ricerca trial. Deve inoltre
verificare che non sia presente una mutazione composta: il gold include una
claim di guardrail su G1202R/L1196M, che non è applicabile al caso singolo.

### C1 — EGFR L858R

Il caso è first-line, avanzato/metastatico, treatment-naive e senza T790M.
FLAURA è applicabile. ADAURA e AURA3 sono fonti documentalmente valide, ma
non applicabili rispettivamente per setting adiuvante/resecato e
post-progressione T790M-positivo. Il risultato corretto non è eliminare queste
fonti, ma mostrarne chiaramente il contesto.

### N1 — RMI2

Il gold è una astensione limitata allo snapshot: “NON DETERMINABILE nello
snapshot congelato”. Non è una dichiarazione che nessuna evidenza esista nel
mondo. Prima del freeze occorre archiviare query, risultato vuoto, hash dello
snapshot e timestamp.

## Regola di freeze

Un caso può diventare `frozen` solo quando:

1. domanda e contesto sono fissati;
2. tutte le claim hanno almeno una fonte primaria;
3. le fonti presenti nel grafo sono state confrontate con il manifest;
4. un secondo annotatore ha revisionato claim, qualificatori e applicabilità;
5. i disaccordi sono stati risolti;
6. per i casi no-answer è disponibile la prova negativa sullo snapshot.
