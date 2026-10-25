# Report finale Stadio 2

Riepilogo consolidato; per il dettaglio vedi i documenti collegati.

- **Chiamate**: 50/50 (25 run_index=1 + 25 run_index=2), 0 retry
  infrastrutturali, 0 hard stop in entrambi i checkpoint
  (`gemma_stage2_protocol.md`, `gemma_run1_checkpoint.md`,
  `gemma_run2_checkpoint.md`).
- **Trasporto**: 88% (run 1), 80% (run 2) — entrambi sotto la soglia del
  90%.
- **Sicurezza**: zero violazioni su tutte e 50 le chiamate (quote
  inesistenti, SourceUnit inventate, campi graph-only, CONTRADICTED
  promosso: tutti a zero) — invariato rispetto allo Stadio 1.
- **Stabilità semantica** (`gemma_run1_run2_stability.md`,
  `gemma_field_stability.md`): 0/17 bundle comparabili instabili; accordo
  del 100% su status finale, esito del validatore e astensione quando il
  trasporto funziona in entrambe le run; zero disaccordi di valore o
  direzione su tutti i 100 slot; il fattore limitante è la disponibilità
  del trasporto (8/25 bundle non comparabili), non l'incoerenza semantica.
- **Utilità incrementale** (`gemma_repeated_incremental_utility.md`): il
  singolo `NEW_VALIDATED_FIELD` dello Stadio 1 si ripete in entrambe le
  run — segnale ripetibile ma marginale (1 campo su 100 slot).
- **Errori ricorrenti** (`gemma_recurring_errors.md`): astensione
  sistematica su 8 bundle specifici; direction errata sistematica su 3;
  nessun errore di sicurezza mai ricorrente.
- **Decisione**: `CLAIM_EXTRACTOR_TRANSPORT_INSUFFICIENT`
  (`gemma_claim_extractor_decision.md`).

Nessuna modifica a prompt, transport, adapter, validatore, EvidenceBundle,
candidate o baseline durante il pilot.
