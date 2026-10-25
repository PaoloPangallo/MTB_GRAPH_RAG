# 03 — CaseContextSemanticVerifier

Quattro livelli distinti. Il verifier testuale esistente **non e' indebolito**:
resta il gate di letteralita' e conserva il potere di veto.

| | Livello | Verifica |
|---|---|---|
| A | TEXTUAL MATCH | il valore compare davvero nel testo |
| B | TYPE COMPATIBILITY | la menzione e' del tipo richiesto dallo slot |
| C | SEMANTIC ROLE COMPATIBILITY | la menzione svolge il ruolo richiesto |
| D | ASSERTION COMPATIBILITY | affermata, non negata |

## Il problema

`febbre` **e'** letteralmente in `Ho la febbre`: il verifier testuale la
accettava come `disease`. Una stringa presente nel testo non e' automaticamente
valida per qualunque slot.

## Tipi ammessi per slot

| Slot | Tipi |
|---|---|
| `disease` | `DISEASE` — **mai** `SYMPTOM` |
| `biomarker` | `GENE` `BIOMARKER` |
| `alteration` | `ALTERATION` |
| `target_intervention` | `INTERVENTION` con ruolo `TARGET_INTERVENTION` |
| `previous_intervention` | `INTERVENTION` con ruolo `PREVIOUS_INTERVENTION` |

Lo slot `disease` richiede inoltre un **ancoraggio oncologico**: senza, il motivo
e' `DISEASE_WITHOUT_ONCOLOGY_ANCHOR`.

## Esiti

`TEXT_MATCH` `TEXT_MISMATCH` `TYPE_MISMATCH` `ROLE_MISMATCH` `NEGATED_MENTION`
`UNCERTAIN_MENTION` `CONTROL_INSTRUCTION_MENTION` `MISSING_IN_TEXT` `ACCEPTED`

Una menzione **incerta** non e' rifiutata: e' accettata con warning. Non
produrra' pero' `FULL_MATCH` nel matching composto.

## Ordine di valutazione

La contaminazione da istruzione di controllo precede ogni altra valutazione: una
menzione dentro uno span di controllo e' rifiutata prima ancora di chiedersi se
il tipo sia corretto.
