# Architettura

Il modulo usa modelli Python separati: `EscatFrameworkReference`, `EscatRule`,
`EscatRuleSet`, `EscatCurationDraft`, `EscatAssessmentRecord` ed
`EscatAssessmentEvent`. La precompilazione legge claim V3, availability
locale e allineamento documentale; non scrive le sorgenti.

Il flusso ?:

```text
qualified claim / provenance / documento locale
        -> prefill read-only
        -> EscatCurationDraft
        -> revisione umana
        -> EscatAssessmentRecord + eventi append-only
        -> adapter dossier opzionale, non collegato a V3
```

`EscatAssessmentRecord` non ? una propriet? della qualified claim. Le
mutazioni del record corrente sono accompagnate da eventi append-only. Una
supersessione crea uno snapshot del record precedente, lo marca
`SUPERSEDED` e crea un nuovo record con `supersedes_assessment_id`; nessun
assessment precedente viene perso.
