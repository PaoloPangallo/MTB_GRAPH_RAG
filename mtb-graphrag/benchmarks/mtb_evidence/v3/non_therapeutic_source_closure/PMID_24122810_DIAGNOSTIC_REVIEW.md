# PMID:24122810 — prima revisione della source unit e dei due claim diagnostici

| | |
|---|---|
| Source unit | `PU-PMID-24122810-cohort-1` |
| Fonte | `PMID:24122810` · DOI `10.1002/hep.26890` |
| Rivista | Hepatology, 2014-04 |
| Materiale usato | abstract indicizzato, SHA-256 `1394c4da90e19d8b…` |
| Stato di accesso | **`full_text_unavailable`** |

## Accesso

Stesso percorso di priorità di `PMID:24662454`: nessun full text locale, nessun
supplemento, nessun record PMC, Unpaywall dichiara `bronze` ma il PDF Wiley
risponde HTTP 402. Resta l'abstract indicizzato, con hash verificato contro la
cache locale.

## Source unit

| Campo | Valore |
|---|---|
| Tipo | coorte di screening di prevalenza molecolare |
| Popolazione | 102 pazienti con colangiocarcinoma (66 intraepatici); coorte di scoperta di 8 specimen senza alterazioni KRAS/BRAF/ROS1 |
| Disease | Colangiocarcinoma, **con risultato ristretto al sottotipo intraepatico** |
| Sample scope | tessuto tumorale; confronto con colorettale (149), epatocellulare (96), gastrico (212) |
| Assay | whole transcriptome sequencing per la scoperta; RT-PCR per lo screening |
| Biomarcatori | FGFR2::AHCYL1 Fusion, FGFR2::BICC1 Fusion |
| Review status | **`first_review_complete`** |
| Indipendenza | `non_independent` |
| Propagation policy | `prototype_only` |
| Hard filterable | `false` |
| Final evaluable | **`false`** |

La unit operativa **non è stata modificata**: resta `awaiting_first_review` nel
corpus. Promuoverne lo stato richiede la seconda revisione indipendente, che non
è avvenuta.

## Findings

| Finding | Locator |
|---|---|
| Identificate due fusioni kinasi, FGFR2-AHCYL1 e FGFR2-BICC1 | UNLABELLED s2 |
| Fusione FGFR2 in 9/102 colangiocarcinomi, esclusivamente intraepatici (9/66, 13,6%) | UNLABELLED s3 |
| Rara in colorettale (1/149) ed epatocellulare (1/96), assente in gastrico (0/212) | UNLABELLED s3 |
| Mutuamente esclusiva con KRAS/BRAF | UNLABELLED s4 |
| Le fusioni ricorrono nel 13,6% dei colangiocarcinomi intraepatici e giustificano una nuova classificazione molecolare | CONCLUSION s0 |

## La decisione sui due claim

Entrambi: **`diagnostic_claim_requires_narrowing`**.

### Cosa la fonte sostiene

Le due fusioni sono identificate per nome. Il ruolo di alterazione che definisce
un sottotipo molecolare è esplicito nel titolo e nella conclusione. La
specificità di malattia è documentata dal confronto con gli altri tumori. La
mutua esclusività con KRAS/BRAF è riportata.

### Cosa richiede un restringimento

`disease_scope`: **`Cholangiocarcinoma` → `Intrahepatic Cholangiocarcinoma`**.

La fonte è esplicita due volte:

> «…detected in nine patients with cholangiocarcinoma (9/102), **exclusively in
> the intrahepatic subtype** (9/66, 13.6%)…» — UNLABELLED s3

> «FGFR2 fusions occur in 13.6% of **intrahepatic** cholangiocarcinoma.» —
> CONCLUSION s0

I claim shadow portano `disease_scope: Cholangiocarcinoma`, ereditato dal grafo.
Lasciarlo così affermerebbe una definizione di sottotipo per una malattia più
ampia di quella misurata — un errore della stessa famiglia di quelli già
corretti su interventi e aggregati, qui sul versante della malattia.

È il motivo per cui la decisione non è `diagnostic_claim_confirmed`: il
contenuto è sostenuto, il perimetro no.

### Cosa non va attribuito

- **prevalenza partner-specifica**: il 13,6% è riportato per «the FGFR2 fusion»
  nel suo insieme, senza alcuna ripartizione fra BICC1 e AHCYL1;
- test diagnostico clinicamente validato;
- sensibilità o specificità diagnostica;
- utilità clinica;
- scelta terapeutica;
- prognosi.

La sensibilità agli inibitori FGFR (BGJ398, PD173074) è mostrata in NIH3T3, non
nei pazienti: è preclinica e appartiene ai claim aggregati di `evidence:1851` e
`evidence:1853`, non a questi claim diagnostici.

Va inoltre notato che la coorte di scoperta era selezionata per **assenza** di
alterazioni KRAS/BRAF/ROS1, il che condiziona la mutua esclusività osservata.

## Esito per claim

| | `evidence:1846` | `evidence:1847` |
|---|---|---|
| Claim ID | `CLM-2175b95ae3113c4f5d97` | `CLM-7056003a9bdef747f514` |
| Biomarcatore | FGFR2::BICC1 Fusion | FGFR2::AHCYL1 Fusion |
| Decisione | `diagnostic_claim_requires_narrowing` | `diagnostic_claim_requires_narrowing` |
| Locator | sufficiente | sufficiente |
| Può diventare final | **no** | **no** |
| Bloccato da | abstract-only, seconda revisione pendente | idem |

I due claim sono stati valutati separatamente e i loro packet di seconda
revisione non si citano a vicenda: il partner di fusione è l'unico campo che li
distingue, e valutarli insieme li renderebbe un solo giudizio.

## Seconda revisione

`SR-evidence-1846.json` e `SR-evidence-1847.json` portano l'abstract, il claim
asserito, le undici domande e il vocabolario delle decisioni ammesse. Non
portano il verdetto del primo reviewer, i suoi reason code, le limitazioni che
ha assegnato né alcuna raccomandazione.
