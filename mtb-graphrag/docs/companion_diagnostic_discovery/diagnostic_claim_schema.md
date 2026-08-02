# Schema di claim diagnostica proposto

Schema concettuale, non implementato:

    {
      "claim_domain": "companion_diagnostic",
      "diagnostic_id": null,
      "diagnostic_name": null,
      "diagnostic_category": null,
      "biomarker": null,
      "disease": null,
      "associated_intervention": null,
      "relation": null,
      "technology": null,
      "specimen_type": null,
      "regulatory_status": null,
      "jurisdiction": null,
      "source": {},
      "parent_record": null,
      "source_unit": null
    }

## Cardinalità e disponibilità

| campo | obbligatorio futuro | disponibilità nel grafo corrente |
|---|---|---|
| claim_domain | sì | proponibile, non materializzato |
| diagnostic_id | sì, se esiste | device_id è presente sui nodi CDx |
| diagnostic_name | sì | device_name è presente sui nodi CDx |
| diagnostic_category | sì | non disponibile come categoria esplicita |
| biomarker | sì | gene_symbol è presente; variante/allele non garantiti |
| disease | sì per una claim disease-specific | manca un legame CDx-specifico |
| associated_intervention | sì per CDx | associated_drug e arco al Drug sono presenti |
| relation | sì | relazione tecnica presente, semantica clinica non completa |
| technology | opzionale | platform_type presente |
| specimen_type | opzionale | specimen_types presente |
| regulatory_status | necessario per una claim regolatoria | non disponibile |
| jurisdiction | necessario per una claim regolatoria | non disponibile |
| source | sì | non presente nel nodo CDx |
| parent_record | sì | non presente nel nodo CDx |
| source_unit | sì | non presente nel nodo CDx |

La source non deve essere riempita dal solo nome del device o dal PMID del
parent. La relazione tra pubblicazione collegata e supporto della claim deve
essere valutata rispetto a un passaggio testuale reale.
