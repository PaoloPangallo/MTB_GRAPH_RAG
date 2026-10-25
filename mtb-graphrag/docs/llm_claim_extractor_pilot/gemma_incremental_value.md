# Valore incrementale rispetto alla baseline B

Criterio C (protocollo, sezione 11): serve almeno uno tra un
`NEW_VALIDATED_FIELD` corretto, un bundle con provenance migliorata, una
ambiguità risolta correttamente, o una contraddizione riconosciuta meglio
della baseline.

| Segnale | Presente |
|---|---|
| Almeno un `NEW_VALIDATED_FIELD` | Sì (1) |
| Bundle con provenance field-level migliorata | Sì (2) |
| Ambiguità risolta correttamente (status migliorato) | No (0) |
| Contraddizione riconosciuta meglio della baseline (`CONFLICTING_FIELD_BLOCKED`) | Sì (26) |

**Segnale presente: sì.** Va però letto con onestà sulla sua reale
grandezza, non solo sul booleano:

- Il `NEW_VALIDATED_FIELD` è **uno solo** su 100 classificazioni possibili:
  il campo `disease` del bundle `EB-42cb660f5be17914df59a8fc`
  (baseline `PARTIAL`, Gemma `ACCEPTED_WITH_DROPPED_FIELDS`), con quota
  letterale e SourceUnit reale. Non è un pattern sistematico, è un singolo
  caso osservato.
- I 2 bundle con "provenance migliorata a status invariato" guadagnano
  citazioni verbatim (quote + SourceUnit) che la sola baseline a regole
  (match booleano per parola chiave) non produce mai — un vantaggio reale
  ma qualitativo, non quantificabile come nuovo status.
- Nessuna ambiguità viene risolta a un livello di status superiore
  (`bundles_status_changed_correctly=0`): Gemma non fa avanzare nessun
  bundle da `PARTIAL`/`AMBIGUOUS` a `DIRECT`, né scopre un nuovo
  `CONTRADICTED` che la baseline non aveva già.
- Le 26 istanze di `CONFLICTING_FIELD_BLOCKED` sono in maggioranza campi
  bloccati dal gate di negazione/contraddizione a livello di intera
  proposta (`REJECTED_CONTRADICTION`/`REJECTED_DIRECTION`, 12 bundle su
  25) — un meccanismo che la baseline a regole non ha affatto, quindi è un
  segnale di sicurezza reale (evita di accettare proposte in conflitto col
  testo), non necessariamente una "contraddizione risolta" nel senso di
  nuova conoscenza prodotta.

In sintesi: il segnale richiesto dal criterio C è tecnicamente presente,
ma è marginale in termini di nuova conoscenza validata (1 campo su 100) e
più solido sul piano della sicurezza/provenance che su quello della resa
informativa netta.
