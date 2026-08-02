# Dati mancanti e limiti

## Mancanze osservate

- I 166 nodi CDx non hanno, nello schema inventariato, source, source unit,
  locator, publication parent o passage.
- Non esiste un legame CDx-specifico con Disease.
- associated_drug e HAS_COMPANION_DIAGNOSTIC non distinguono associazione,
  selezione terapeutica e requisito d'uso.
- gene_symbol non è una normalizzazione completa di variante o fusione.
- platform_type descrive una tecnologia ma non documenta validazione,
  prestazioni o approvazione.
- specimen_types è un elenco riportato, non una relazione di requisito.
- Non sono presenti categoria complementary, screening o confirmation.
- Non risultano stato regolatorio, giurisdizione, data/versione o fonte CDx.
- Le due claim attive hanno provenance e locator del PMID, ma non un device
  associato.

## Perché gli altri record non sono claim

Il flusso V3 materializza claim a partire da Evidence auditato e adattato.
Le query CDx sono presenti in percorsi legacy di target/subgraph e in una
ablation RAG, ma non alimentano v2_adapter, shadow claim builder o
materialization. I record CDx vengono quindi visualizzati o aggregati nei
risultati legacy, non materializzati come claim diagnostiche.

## Distinzioni non risolvibili

Con i dati correnti non è possibile distinguere in modo affidabile:

- diagnostica generica da companion diagnostic;
- companion da complementary diagnostic;
- screening da test di conferma;
- associazione di farmaco da requisito per la terapia;
- gene-level detection da variant/partner-specific detection;
- relazione terminologica da applicabilità clinica.

La label e il nome dell'arco sono evidenze dello schema, non una licenza per
inferire una categoria regolatoria o una relazione di efficacia.
