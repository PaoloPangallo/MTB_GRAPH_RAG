# Migration specification emendata

Versione: `migration_specification_amended/1.1`
Sostituisce: `migration-specification/1.0` (SHA `20d6399634e577a72b06bac5bb0943e29bf548b96e4ad47107180dcb4423ed3b`)
Stato: `amended_not_promoted`
Erratum collegato: `adjudication_erratum/1.0`

L'originale è conservato dov'è e non è stato modificato. Questa versione lo
sostituisce dichiarandolo: le sezioni non emendate restano quelle di prima e sono
elencate per nome, così che la differenza fra le due versioni sia esattamente
leggibile invece che ricostruibile per confronto.

## Sezioni emendate

**§16 — Deprecazione degli statement esistenti.** Corretta secondo l'erratum B:
i due gruppi senza claim sostitutivo sono `evidence:3811` ed `evidence:4759`.
`evidence:275` ha un sostituto aggregato.

**§21 — Tassonomia degli oggetti del repository** *(nuova)*. Il repository
contiene cinque categorie distinte e non sovrapponibili:

| Categoria | Descrizione | Therapy score |
|---|---|---|
| Claim terapeutici | atomici, aggregati, di regime — portano un intervento | sì |
| Claim non terapeutici | diagnostici, prognostici — non portano intervento | no |
| Associazioni unsupported | conclusioni negative auditabili | no |
| Associazioni unresolved | sospensioni riapribili | no |
| Parent senza claim | contenitori per cui nessun claim è sostenuto | no |

Le cinque categorie hanno denominatori separati: nessuna metrica le somma.

**§22 — Claim non terapeutici** *(nuova)*. `DiagnosticClaim` e `PrognosticClaim`
sono fratelli di `TherapeuticClaim` sotto `EvidenceClaim`, non suoi sottotipi.
Non ricevono therapy score, non entrano nelle metriche therapy-level, non
vengono appiattiti in `intervention`, non sono confrontabili con regimi o classi.
`PredictiveClaim` non viene introdotto.

## Inventario emendato

| Categoria | Conteggio |
|---|---|
| Parent | 147 |
| Claim terapeutici | 146 (140 atomici, 3 aggregati, 3 regimi) |
| Claim diagnostici | 2 |
| Claim prognostici | 0 |
| **Totale claim** | **148** *(derivato)* |
| Associazioni unsupported | 6 |
| Associazioni unresolved | 6 |
| Parent senza claim | 3 (`evidence:347`, `evidence:3811`, `evidence:4759`) |
| Statement legacy deprecati | 15 (13 + 2 sostituiti da claim diagnostico) |
| Statement senza sostituto positivo | 2 (`evidence:3811`, `evidence:4759`) |

## Impatto sui piani di rigenerazione

Nessun piano è eseguito in questa fase.

| Piano | Prima | Aggiunta | Dopo |
|---|---|---|---|
| Qualification link da creare | 15 | 2 | 17 |
| Qualification link da ritirare | 13 | 2 | 15 |
| View da rigenerare | 13 | 2 | 15 |

## Cosa resta invariato

Tutte le altre sezioni della specification originale. I 15 claim terapeutici
adjudicati e i loro `claim_id`. Le 12 associazioni. Il repository shadow, che non
è stato rigenerato. Il corpus operativo, l'adapter, il retriever, lo scoring.
