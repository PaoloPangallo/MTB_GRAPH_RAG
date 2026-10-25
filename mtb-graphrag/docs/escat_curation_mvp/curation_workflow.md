# Workflow di curation

1. `list-claims` e `show-claim` permettono di selezionare una claim.
2. `create-draft` precompila soltanto valori presenti nei record locali e
   genera `DRAFT_CREATED` e `FIELD_PREFILLED`.
3. `show-draft` e `show-missing-fields` mostrano lo stato corrente.
4. `edit-field`, `set-curator`, `set-rationale`, `attach-source` e
   `attach-passage` validano e registrano ogni modifica.
5. `select-rule` richiede un rule set caricato e strutturalmente valido; non
   assegna tier o subtier.
6. `set-status CURATED` richiede una validazione positiva. In assenza del rule
   set ufficiale non ? possibile curare un tier.
7. `validate-assessment` registra sempre `ASSESSMENT_VALIDATED` con l'esito.
8. `reject-assessment` registra il cambio di stato e
   `ASSESSMENT_REJECTED`.
9. `supersede-assessment` conserva uno snapshot del record precedente,
   porta il precedente a `SUPERSEDED` e crea una nuova bozza con riferimento
   `supersedes_assessment_id`.
10. `export-dossier` copia lo stato reale senza dedurlo dalla presenza del
    tier.

## Transizioni

```text
DRAFT -> INCOMPLETE -> READY_FOR_REVIEW -> CURATED
DRAFT, INCOMPLETE, READY_FOR_REVIEW, CONFLICTING_EVIDENCE, NOT_APPLICABLE -> REJECTED
CURATED, REJECTED, CONFLICTING_EVIDENCE, NOT_APPLICABLE -> SUPERSEDED
```

Le transizioni invalide sono rifiutate e registrate come tentativo
`STATUS_CHANGED` con motivazione `INVALID_STATUS_TRANSITION`; lo stato non
viene modificato. `NOT_APPLICABLE` e `CONFLICTING_EVIDENCE` non diventano
implicitamente `INCOMPLETE`.

## Rule set

Il file `test_fixture_ruleset.json` serve soltanto ai test ed ? marcato
`TEST_FIXTURE_ONLY` / `NOT_AN_OFFICIAL_ESCAT_RULESET`. Non ? usato dal pilota
e non ? una valutazione scientifica.
