# Disease policy options

## Contratto della simulazione

Le quattro policy sono state dichiarate prima del calcolo, applicate alle stesse
righe V2 congelate e contate sia come righe sia come graph evidence ID. Il gold
non è stato caricato. I conteggi sono descrittivi e non sono metriche cliniche.

| Policy | EGFR righe / graph ID | FGFR2 righe / graph ID |
|---|---:|---:|
| A — strict exact + alias verificati | 38 / 32 | 1 / 1 |
| B — explicit ontology-aware | 48 / 42 | 11 / 8 |
| C — broad generation, soft disease | 56 / 48 | 17 / 14 |
| D — V2 high-recall + V3 qualification | 81 / 73 | 28 / 25 |

## A — strict exact

Ammette stesso ID, normalized exact e alias già verificati. È altamente
spiegabile e non richiede modifiche al corpus. Per EGFR rende operativo soltanto
l’alias NSCLC indipendentemente verificato; `Lung Adenocarcinoma` non è incluso
come sinonimo e non recupera contesti generici. Per FGFR2 resta a un solo iCCA
exact.

Rischio: perdita di etichette parent/child. Impatto: allineamento esplicito del
contratto alias del filtro, senza nuovi sinonimi.

## B — explicit ontology-aware

Aggiunge soltanto parent/child espliciti negli artefatti locali. Porta EGFR a
48 righe/42 graph ID includendo `Lung Adenocarcinoma` come sottotipo con
warning, e porta FGFR2 a
11 righe/8 graph ID grazie a `iCCA → cholangiocarcinoma`. Non include
`Cholangiolocellular Carcinoma`, che è un sibling e non un parent/child.

Rischio: il parent più ampio può aumentare contesti non applicabili. Richiede
warning, score distinto, policy review e una rappresentazione stabile della
provenance gerarchica. Non richiede equivalenze nuove.

## C — broad candidate generation, soft disease ranking

Mantiene tutti i record biomarker-compatible: 56/48 EGFR e 17/14 FGFR2. Il
disease diventa segnale di ranking, warning e audit. Conserva visibilità sui
contesti non risolti senza chiamarli disease-compatible.

Rischio: più falsi positivi e top-k occupato da cross-disease. È compatibile con
GraphRAG, ma richiede una modifica esplicita della candidate generation e una
review della policy; non è una normalizzazione stringa.

## D — V2 high-recall + V3 qualification

Usa l’intero pool V2 e delega alla V3 classificazione, penalità, warning e
provenance. Conserva 81/73 EGFR e 28/25 FGFR2, ma include 25 record EGFR e 11
record FGFR2 che falliscono il biomarcatore post-fix; tra questi vi sono quattro
righe FGFR1.

Rischio: il pool mescola source-, drug- e gene-neighborhood e richiede un
provider ibrido, audit rigoroso e separazione primaria/audit-only. Non è pronto
senza una decisione sull’adapter multi-intervento e sulle semantiche V2.

## Conclusione di policy

La sola correzione tecnicamente pronta è l’allineamento agli alias già
verificati (parte di A). B, C e D sono opzioni architetturali, non bug fix. La
review non ne seleziona una sulla base del gold o di un possibile aumento di
coverage.
