# 02 — Contratto CaseContext 2.0

`case-context/2.0`, **additivo**: i campi scalari di 1.0 restano intatti e
nessun consumatore esistente si rompe.

## Perche' derivato, non richiesto al parser

Le menzioni tipizzate sono costruite deterministicamente **dall'output del
parser esistente**, senza toccare prompt ne' schema della tool call:

* il prompt e' congelato nel benchmark RQ4 (`casecontext-parser-prompt/1.0`,
  hash `7b59558b...`) e cambiarlo invaliderebbe il gold;
* la distinzione fra menzione e campo accettato e' una proprieta'
  **deterministica** del testo. Chiederla al parser significherebbe far decidere
  all'LLM cio' che il gate deve decidere.

## Strutture aggiunte

```json
{
  "contract_version": "case-context/2.0",
  "disease_mentions": [], "gene_mentions": [], "alteration_mentions": [],
  "biomarker_observations": [], "intervention_mentions": [],
  "symptom_mentions": [], "contradictions": [],
  "control_instruction_spans": [], "parser_uncertainties": [],
  "rejected_mentions": []
}
```

## Campi di una menzione

`raw_text`, `normalized_value`, `entity_type`, `semantic_role`,
`assertion_status`, `source_span`, `parser_confidence`,
`accepted_for_casecontext`, `rejection_reason`, `slot`, `warnings`.

| Enum | Valori |
|---|---|
| `entity_type` | `DISEASE` `GENE` `ALTERATION` `BIOMARKER` `INTERVENTION` `SYMPTOM` |
| `assertion_status` | `ASSERTED` `NEGATED` `UNCERTAIN` `HYPOTHETICAL` `HISTORICAL` `UNKNOWN` |
| `semantic_role` (intervention) | `TARGET_INTERVENTION` `PREVIOUS_INTERVENTION` `CURRENT_INTERVENTION` `COMPARATOR` `CONTEXTUAL_MENTION` `CONTROL_INSTRUCTION_MENTION` `UNKNOWN` |

## La regola architetturale

```
ENTITY_MENTION  !=  ACCEPTED_CASECONTEXT_FIELD
```

Una menzione rifiutata **resta visibile** con il proprio `rejection_reason`. Non
viene cancellata: sparirebbe dall'audit.

## Negazione limitata alla frase

In `Lung adenocarcinoma. EGFR testing was negative.` il negativo riguarda EGFR,
non la malattia. Una finestra a caratteri fissi le confondeva; la finestra e' ora
la frase.

I qualificatori di stato genico (`wild-type`) negano **solo** un'alterazione
adiacente, non l'intera frase: `Colorectal cancer, KRAS wild-type` lascia
asserite sia la malattia sia il gene.
