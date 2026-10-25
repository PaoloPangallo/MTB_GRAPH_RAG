# Error and abstention model — contratto congelato (Fase B)

Requisito §15 del prompt: *"Non trasformare nessun risultato, astensione, errore
e warning in uno stesso stato generico."*

Il modello non è proposto: i valori sono **estratti** da `models.py`,
`pipeline.py` e `deterministic_pipeline.py` @ `6ee64c5`.

## 1. Le quattro classi, tenute distinte

| Classe | Significato | Colore/segno UI | La pipeline prosegue? |
|---|---|---|---|
| **ESITO** | la pipeline ha prodotto un risultato | neutro | sì |
| **ASTENSIONE** | un componente ha deliberatamente non deciso | ambra, icona dedicata | sì |
| **WARNING** | risultato prodotto con riserva | ambra, bordo | sì |
| **ERRORE** | un componente non ha potuto operare | rosso | dipende |

L'astensione **non è** un errore: è il comportamento corretto dell'enricher
quando non trova supporto letterale. Presentarla come fallimento
travisererebbe l'architettura.

Nessuno stato è indicato dal solo colore: ogni classe ha etichetta testuale e
icona (§19 accessibilità).

## 2. Arresti della pipeline — `stopped_at`

Da `pipeline.py::run_case`. Sono gli unici quattro punti in cui la run termina
prima del dossier.

| `stopped_at` | Stage | Classe | Significato |
|---|---:|---|---|
| `PARSER_TRANSPORT_FAILED` | 2 | ERRORE | il transport LLM non ha restituito un tool call valido |
| `CASECONTEXT_MISMATCH` | 3 | ESITO | un campo essenziale non trova riscontro nel testo — **arresto corretto**, non guasto |
| `RETRIEVAL_NO_MATCH` | 4–5 | ESITO | il grafo non propone candidate |
| `CALL_BUDGET_EXCEEDED` | 2 o 9 | ERRORE | superato `MAX_REAL_CALLS_TOTAL = 20` |

`CASECONTEXT_MISMATCH` e `RETRIEVAL_NO_MATCH` sono **esiti legittimi**: la
pipeline si è fermata perché doveva. Il Caso 5 del pilot è esattamente questo.
La UI non deve colorarli di rosso.

Gli stage successivi a un arresto sono `SKIPPED`, mai `FAILED`.

## 3. Verifica del CaseContext — `MATCH_STATUSES`

Da `models.py`. Per ciascuno dei 6 `MATCH_FIELDS`:

| Status | Classe | Blocca? |
|---|---|---|
| `MATCH` | ESITO | no |
| `MISMATCH` | ESITO | sì, se il campo è essenziale |
| `UNCERTAIN` | WARNING | no |
| `MISSING_IN_TEXT` | WARNING | no |

La decisione di blocco è di `verifier.essential_fields_pass()`, deterministica.
La UI mostra l'esito campo per campo con `supporting_text`, offset e
`reason_code`, e riporta la decisione — non la ricalcola.

Nota architetturale registrata nel pilot: il verifier **non si fida degli offset
autodichiarati dal modello**. È una proprietà di sicurezza da preservare.

## 4. Enrichment — i 10 outcome

Da `models.py::ENRICHMENT_OUTCOMES`. È il vocabolario più ricco del sistema e
copre da solo gran parte della §15.

| Outcome | Classe | Entra nel calcolo dello status? |
|---|---|---|
| `ENRICHMENT_ACCEPTED` | ESITO | **sì** |
| `ENRICHMENT_ACCEPTED_WITH_WARNING` | WARNING | **sì** |
| `ENRICHMENT_ABSTAINED` | ASTENSIONE | no |
| `REJECTED_QUOTE` | ERRORE di validazione | no |
| `REJECTED_SOURCE_UNIT` | ERRORE di validazione | no |
| `REJECTED_DOCUMENT` | ERRORE di validazione | no |
| `REJECTED_CONTEXT_MISMATCH` | ERRORE di validazione | no |
| `REJECTED_SUMMARY_UNGROUNDED` | ERRORE di validazione | no |
| `REJECTED_SCHEMA` | ERRORE di transport | no |
| `REJECTED_TRANSPORT` | ERRORE di transport | no |

Solo i primi due passano a `evaluate_association`. È l'invariante §5 del design:
**un enrichment non validato non può influenzare status, mask, gate o bucket.**

Misure reali della run v2 `6ee64c5`, da mostrare come contesto sperimentale:

| Outcome | n |
|---|---:|
| `ENRICHMENT_V2_ACCEPTED` | 2 |
| `REJECTED_QUOTE_NOT_FOUND` | 1 |
| `ENRICHMENT_V2_ABSTAINED` | 2 |
| `ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS` | 2 |

Su 7 chiamate: 3 QUOTE, 4 ABSTAIN, 2 quote accettate, 0 SourceUnit inventate
accettate, 0 raccomandazioni cliniche. **L'astensione è l'esito più frequente e
va presentata come normale.**

## 5. Status e mask — nessun esito generico

Da `deterministic_pipeline.py`. Ogni combinazione produce uno status distinto:

| Condizione | `status` | `gate_bucket` | `direction` mask |
|---|---|---|---|
| intent `THERAPY_DISCOVERY` | `DISCOVERED` | `DISCOVERY_BUCKET` | `NOT_APPLICABLE` |
| nessun enrichment validato | `AMBIGUOUS` | `WARNING_BUCKET` | `NO_DOCUMENT_SIGNAL` |
| almeno una `CONFLICTING` | `CONTRADICTED` | `REJECTED_BUCKET` | `CONTRADICTED` |
| almeno una `CONSISTENT`, senza warning | `DIRECT` | `PRIMARY_BUCKET` | `SUPPORTED` |
| almeno una `CONSISTENT`, con warning | `PARTIAL` | `WARNING_BUCKET` | `SUPPORTED` |
| solo `UNRELATED` | `PARTIAL` | `WARNING_BUCKET` | `UNRELATED_EVIDENCE` |

Warning deterministici emessi: `NO_VALIDATED_ENRICHMENT_AVAILABLE`,
`SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING`,
`VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION`.

`AMBIGUOUS` con `NO_DOCUMENT_SIGNAL` è il caso più delicato: significa *"il
grafo propone la candidate, nessun documento validato la conferma o la smentisce"*.
Non è né supporto né contraddizione, e la UI deve dirlo per esteso.

## 6. Errori infrastrutturali

Non appartengono al dominio e vanno tenuti separati: flag disattivato,
dati congelati non trovati, ledger non scrivibile, timeout del provider LLM.

Resa: `STAGE_FAILED` con `reason_code` dedicato e `producer.kind` invariato. Mai
riclassificati come astensione.

## 7. Regole di presentazione

1. mai un badge unico "errore" per classi diverse;
2. un'astensione mostra sempre `abstention_reason` testuale;
3. un rigetto mostra sempre quale controllo ha fallito;
4. uno stage `SKIPPED` mostra **perché** (lo `stopped_at` a monte);
5. un errore backend **non** diventa un risultato positivo: nessun fallback che
   trasformi un guasto in un dossier;
6. se il backend è offline la UI mostra lo stato di errore, non dati simulati.

## 8. Test richiesti

- ogni valore di `stopped_at` produce lo stato UI atteso e stage `SKIPPED`;
- gli 8 outcome non accettati non alterano status, mask, gate, bucket;
- `CASECONTEXT_MISMATCH` non è reso come errore;
- un'astensione non è resa come fallimento;
- backend offline → stato di errore, mai risultato;
- nessun payload di evento contiene chain-of-thought.
