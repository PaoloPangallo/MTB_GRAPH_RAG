# Separazione della provenance

Il dossier mantiene distinti:

| Concetto | Campo |
|---|---|
| Claim provenance | `provenance.claim_sources` |
| Document support | `document_support` |
| ESCAT rule source | `provenance.rule_sources` |
| Assessment supporting sources | `assessment_supporting_sources` and `clinical_actionability.supporting_sources` |
| Assessment passages | `supporting_passages` and `clinical_actionability.supporting_passages` |

Un PMID della claim non viene copiato automaticamente nell’assessment. La fonte
del framework/ruleset non è una fonte di supporto della claim. Il layer copia
le collezioni separatamente e non le unifica.
