# Architettura

Il modulo usa modelli Python separati: `EscatFrameworkReference`, `EscatRule`,
`EscatRuleSet`, `EscatCurationDraft`, `EscatAssessmentRecord` ed
`EscatAssessmentEvent`. La precompilazione legge claim V3, availability
locale e allineamento documentale; non scrive le sorgenti.

Il flusso è:

```text
qualified claim / provenance / documento locale
        -> prefill read-only
        -> EscatCurationDraft
        -> revisione umana
        -> EscatAssessmentRecord + eventi append-only
        -> adapter dossier opzionale, non collegato a V3
```

`EscatAssessmentRecord` non è una proprietà della qualified claim. Un
assessment precedente resta immutato; una sostituzione usa
`supersedes_assessment_id` e un evento esplicito.
