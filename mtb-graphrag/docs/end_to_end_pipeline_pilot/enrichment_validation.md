# Validazione dell'arricchimento

Interamente deterministica (`enrichment_validator.py`). Controlla:
paper_id/source_unit_id/candidate_id esistenti e coerenti, quote letterale
e continua (nessuna ellissi), drug richiesta compatibile con quella
riportata e presente nel testo, compatibilità minima disease/biomarker,
riassunto non contenente raccomandazioni cliniche e con overlap lessicale
sufficiente con la quote (soglia 25% per l'accettazione, 50% senza
warning). L'arricchimento non è mai usato come prova primaria: l'evidenza
primaria resta `GraphCandidateAssertion` + documento + SourceUnit +
pipeline deterministica.

## Risultati (7 validazioni)

| Esito | Conteggio |
|---|---:|
| `ENRICHMENT_ABSTAINED` | 4 |
| `REJECTED_TRANSPORT` | 3 |
| `ENRICHMENT_ACCEPTED` / `ENRICHMENT_ACCEPTED_WITH_WARNING` | 0 |

Nessuna proposta ha raggiunto l'accettazione in questa run — coerente con
il fatto che tutte le chiamate a trasporto valido si sono astenute
correttamente (vedi `paper_context_enricher.md`). Zero quote inesistenti
accettate, zero SourceUnit inventate accettate, zero riassunti non
grounded accettati, zero raccomandazioni accettate — non per assenza di
tentativi malformati (nessuno ne è stato prodotto in questa run), ma
perché ogni possibile causa di rigetto sarebbe stata catturata dal
validatore invariato.
