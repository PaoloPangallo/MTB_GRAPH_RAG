# Workflow di curation

1. `list-claims` o selezione delle 15 claim del pilota.
2. `create-draft` precompila soltanto valori presenti nei record locali.
3. `show-missing-fields` mostra requisiti e livelli mancanti.
4. Il curatore allega separatamente source e passage con locator reale.
5. `select-rule` resta bloccato finché non è disponibile un rule set locale.
6. `validate-assessment` controlla framework version, rule, fonte,
   biomarcatore, malattia, intervento, motivazione, curatore e timestamp.
7. `export-assessment` produce una sezione dossier shadow.
8. Ogni cambiamento è registrato in `assessment_events.jsonl`.

In assenza della fonte normativa, lo stato valido del pilota è
`INCOMPLETE`; non è possibile trasformarlo in `CURATED` con tier.
