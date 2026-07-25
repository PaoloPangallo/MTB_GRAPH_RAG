# Readiness dell'adjudication

`comparison_type = first_review_vs_blinded_non_independent_replicate`

| criterio | stato |
| --- | --- |
| `reviews_aligned` | true |
| `all_groups_compared` | true |
| `all_interventions_compared` | true |
| `descriptive_agreement_available` | true |
| `independent_agreement_available` | false |
| `provisional_consensus_available` | true |
| `adjudication_packets_complete` | true |
| `guideline_refinement_ready` | true |
| `ready_for_adjudication` | true |
| `ready_for_adapter_migration` | false |

## Cosa e' pronto

12 gruppi hanno un packet completo: contesto documentale, decisione e
razionale di entrambe le revisioni, differenze evidenziate e domande binarie o
categoriali. Nessun packet contiene una decisione precompilata, metriche gold, risultati
di retrieval o suggerimenti basati sul recall.

1 gruppo soddisfa i criteri del consenso provvisorio, e resta comunque
`prototype_only`.

## Cosa resta chiuso

`independent_agreement_available` e' falso e non puo' diventare vero con questi dati: la
replica non e' indipendente, e nessuna elaborazione successiva puo' produrre indipendenza
a posteriori. Servirebbe una terza revisione condotta senza contaminazione di contesto.

`ready_for_adapter_migration` resta falso perche' presuppone l'adjudication, che non e'
stata fatta. La domanda strutturale — il parent e' un claim o un contenitore — non e'
decisa, e da sola sposta il numero di statement risultanti.
