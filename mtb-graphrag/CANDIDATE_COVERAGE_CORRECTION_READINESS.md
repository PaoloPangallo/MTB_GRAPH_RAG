# Candidate coverage correction readiness

Baseline confrontata: `ec2293baed1202edc9027fdb173a0aa25c1961f4`. Il manifest identifica il generatore tramite SHA-256 canonico dello script.

```json
{
  "root_causes_identified": true,
  "technical_bug_fix_ready": true,
  "normalization_fix_ready": false,
  "corpus_regeneration_required": true,
  "semantic_review_required": true,
  "ready_to_restore_v2_coverage": false,
  "ready_to_rerun_exploratory_evaluation": false
}
```

Il bug tecnico pronto per una fase separata è il match del biomarcatore:
quando gene e alterazione sono entrambi richiesti, il prototipo corrente accetta
uno dei due. I 23 extra ALK lo dimostrano senza riferimento al gold.

La perdita EGFR non è pronta per una correzione automatica. La forma
`Lung Non-small Cell Carcinoma` non coincide con le chiavi della query, ma una
mappatura `carcinoma`/`cancer` deve essere versionata e revisionata. La perdita
FGFR2 è prevalentemente una differenza attesa: i traversal V2 per gene, farmaco
o fonte erano più larghi dei vincoli disease/biomarker V3.

Per ripristinare la rappresentazione record-level V2 servirebbe inoltre
rigenerare l'adapter e poi il corpus, perché 11 righe multi-intervento sono
canonicalizzate in statement con un solo intervento. Non è necessario farlo per
preservare l'identità del graph evidence ID.

Il nuovo confronto esplorativo resta bloccato finché:

- il fix congiuntivo gene/alterazione non è implementato e verificato in un
  commit separato;
- la disease normalization non è approvata o esplicitamente lasciata invariata;
- viene deciso se la parità desiderata è per graph evidence, statement, fonte o
  proposizione, non per righe V2.

Nessun peso, soglia, sinonimo, corpus o risultato precedente è stato modificato.
