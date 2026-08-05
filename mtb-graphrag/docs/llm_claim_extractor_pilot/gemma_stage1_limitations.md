# Limiti dello Stadio 1

Un solo `run_index` per bundle (nessuna ripetizione): non misura la
stabilità tra run ripetute sullo stesso bundle. Lo Stadio 2 (le altre due
run) non è stato autorizzato ed eseguito, quindi questo resta uno sguardo a
una sola osservazione per bundle, non una stima di varianza.

Il campione dei 25 bundle è sbilanciato per tipo (`PARTIAL`=11,
`AMBIGUOUS`=11, `CONTRADICTED`=2, `DIRECT`=1): i criteri A/B/C sono
applicati in modo diseguale — un solo bundle copre il criterio A, due il
criterio C.

Il tasso di fallimento del transport (68% validi contro 100% nei 3 bundle
dello smoke) può dipendere da fattori non isolati in questo Stadio 1:
lunghezza/complessità del documento, numero di SourceUnit, o
caratteristiche specifiche dei singoli bundle non ancora analizzate una per
una. Questo report non include un'analisi di correlazione tra dimensione
dell'input e fallimento del transport.

La cache documenti (`data_cache/document_grounding/`) è stata usata in sola
lettura, invariata dal pilot MiniMax; non è stata ricostruita né validata
contro una nuova fetch di rete in questa sessione.

Le risposte raw dei modelli non sono committate (solo hash); l'analisi
qualitativa si basa sulle proposte canoniche post-adapter e sui
`reason_codes`, non sul testo grezzo generato dal modello.

I due casi `REJECTED_CONTRADICTION` per negazione non preservata
(`gemma_stage1_validation.md`) non sono stati approfonditi oltre il
reason_code del validatore — non è noto se il modello abbia effettivamente
"visto" la negazione e scelto di ometterla, o se non l'abbia rilevata
affatto (il campo `thinking` è vuoto per `think=False` onorato, quindi non
c'è traccia di ragionamento intermedio da ispezionare).
