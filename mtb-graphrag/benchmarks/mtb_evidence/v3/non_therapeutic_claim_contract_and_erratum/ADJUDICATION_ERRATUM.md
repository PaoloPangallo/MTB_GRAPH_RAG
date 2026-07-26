# Erratum agli artefatti di adjudication e alla migration specification

Versione: `adjudication_erratum/1.0`
Data: 2026-07-26
Artefatti originali: **non modificati**

Nessun artefatto congelato è stato riscritto. La correzione vive accanto
all'originale, ne cita l'hash e il lineage tiene i due collegati: chi legge
l'originale può risalire alla rettifica, chi legge la rettifica può verificare
l'originale. Nessuna decisione documentale dell'adjudication è stata riaperta.

---

## Correzione A — conteggio dei claim

| | |
|---|---|
| Artefatto | `multi_intervention_adjudication/post_adjudication_schema_simulation.json` |
| SHA-256 originale | `ddd7bcf04b45c60ea89f230918c0ee46277068b248934b4c6cb57a778ceba95f` |
| Campo | `resulting_claim_count` |
| Valore originale | `149` |
| Valore corretto | `148` |
| Base della correzione | derivato dall'audit |

**Causa.** La proiezione `147 − 13 + 15` assumeva che ognuno dei 134 record non
adjudicati portasse un claim. Tre non ne portavano. Il numero non era sbagliato
per un errore di conto: era sbagliato perché la tassonomia era incompleta.
Conteneva solo tipi di intervento, e tre record non affermano una terapia.

**Derivazione del valore corretto.**

| | |
|---|---|
| Claim terapeutici (invariati dal repository shadow) | 146 |
| Claim diagnostici approvati dall'audit | 2 |
| Claim prognostici approvati dall'audit | 0 |
| **Totale** | **148** |

Il valore non è stato scelto: è il risultato dell'audit dei tre record. Due sono
diventati claim diagnostici, uno resta sospeso. Se l'audit avesse approvato anche
`evidence:347` il totale sarebbe stato 149, e sarebbe stato altrettanto derivato.

**Impatto sulla migrazione.** Il denominatore claim-level cambia e va etichettato
con la versione del corpus. Due statement legacy passano da «preservato come
claim legacy migrato» a «sostituito da claim diagnostico»: gli statement
deprecati passano da 13 a 15.

**Impatto sulle decisioni documentali.** Nessuno.

---

## Correzione B — gruppi senza claim sostitutivo

| | |
|---|---|
| Artefatto | `multi_intervention_adjudication/migration_specification.json` |
| SHA-256 originale | `20d6399634e577a72b06bac5bb0943e29bf548b96e4ad47107180dcb4423ed3b` |
| Campo | `sections.16_deprecation.content` |
| Ricompare in | `ADAPTER_MIGRATION_SPECIFICATION.md`, riga 68 (SHA `b92a3daf…`) |
| Base della correzione | i dati strutturati contraddicono la prosa |

**Testo originale**

> Due di essi (`evidence:275` ed `evidence:4759`) non hanno alcun claim
> sostitutivo e la deprecazione va motivata col reason code.

**Testo corretto**

> Due di essi (`evidence:3811` ed `evidence:4759`) non hanno alcun claim
> sostitutivo e la deprecazione va motivata col reason code. `evidence:275` ha
> invece un claim sostitutivo, aggregato sulla classe EGFR-TKI: ciò che non ha è
> un sostituto atomico su erlotinib, ed è esattamente il punto
> dell'adjudication.

**Causa.** Errore di redazione. `evidence:275` è il gruppo il cui claim
*atomico* è stato rifiutato, e nella frase è stato scambiato con il gruppo che
non ha alcun claim.

**Fonti strutturate della correzione** — quattro artefatti concordano contro
quella frase:

| Artefatto | Contenuto |
|---|---|
| `packet_adjudications.jsonl` | `evidence:275` → `approved_claims: ['CLM-4ffe85304f3ef5533b58']`; `evidence:3811` e `evidence:4759` → `approved_claims: []` |
| `post_adjudication_schema_simulation.json` | `groups_without_any_claim: ['evidence:3811', 'evidence:4759']` |
| `MULTI_INTERVENTION_ADJUDICATION.md`, riga 23 | «gruppi che non producono alcun claim: 2 (`evidence:3811`, `evidence:4759`)» |
| `PARENT_SEMANTICS_DECISION.md`, riga 67 | «Un gruppo può restare senza alcun claim, come `evidence:3811` e `evidence:4759`» |

**Correzioni puntuali**

| Gruppo | Stato corretto |
|---|---|
| `evidence:275` | **ha** un claim sostitutivo: `CLM-4ffe85304f3ef5533b58`, `aggregate_intervention_claim` sulla classe `EGFR tyrosine kinase inhibitor`. Non ha un sostituto atomico. |
| `evidence:3811` | **nessun** claim positivo sostitutivo. 3 associazioni unresolved, full text richiesto. |
| `evidence:4759` | **nessun** claim positivo sostitutivo. 2 associazioni unsupported. |

**Impatto sulla migrazione.** Nessuno: la migrazione shadow aveva già seguito i
dati strutturati e non la prosa. L'impatto è su chi legge la specification e ne
trarrebbe una conclusione sbagliata su `evidence:275`.

**Impatto sulle decisioni documentali.** Nessuno.

---

## Cosa l'erratum non fa

Non riapre alcuna decisione dell'adjudication. Non tocca i 15 claim approvati, le
12 associazioni, i `claim_id` congelati. Non promuove il repository shadow, che
resta byte per byte quello generato nella fase precedente. Non usa il gold.
