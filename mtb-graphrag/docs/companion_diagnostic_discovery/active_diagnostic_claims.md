# Claim diagnostiche attive

Il repository V3 contiene due claim attive con claim_domain diagnostic.
Sono state confrontate con il record originale, il parent, la source unit e
il PMID già documentato dal pilota PMID.

## CLM-8941c177da91f66ff93a

| campo | valore |
|---|---|
| parent_id | GEP-f73a180a63fd22932198 |
| graph_evidence_id | evidence:1846 |
| biomarker | FGFR2::BICC1 Fusion |
| disease | Intrahepatic Cholangiocarcinoma |
| diagnostic_subject | FGFR2::BICC1 Fusion come alterazione che definisce un sottotipo molecolare |
| interpretation | subtype_defining_alteration |
| assay/method | whole transcriptome sequencing; RT-PCR screening |
| population/sample scope | 102 pazienti con colangiocarcinoma, di cui 66 intraepatici, con confronti tra altri tumori |
| relation/direction | diagnostic, supports |
| intervention | assente |
| source unit | PU-PMID-24122810-cohort-1 |
| PMID/locator | PMID:24122810; abstract sentences 2/3/4 e conclusion |
| provenance | PMID claim-linked, abstract indexed; full text unavailable |

La claim è classificabile solo come diagnostic evidence/subtype definition.
Il testo locale non afferma utilità clinica del test, approvazione, terapia
richiesta o efficacia terapeutica. Nel pilota PMID il supporto è DIRECT_SUPPORT
per gli elementi essenziali della claim, con le limitazioni registrate nel
report.

## CLM-a7e1c40b794d2c4d4ca8

| campo | valore |
|---|---|
| parent_id | GEP-1b7a5d64d605bc2a92c1 |
| graph_evidence_id | evidence:1847 |
| biomarker | FGFR2::AHCYL1 Fusion |
| disease | Intrahepatic Cholangiocarcinoma |
| diagnostic_subject | FGFR2::AHCYL1 Fusion come alterazione che definisce un sottotipo molecolare |
| interpretation | subtype_defining_alteration |
| assay/method | whole transcriptome sequencing; RT-PCR screening |
| population/sample scope | stessa coorte e confronti tumorali dell'altra claim |
| relation/direction | diagnostic, supports |
| intervention | assente |
| source unit | PU-PMID-24122810-cohort-1 |
| PMID/locator | PMID:24122810; abstract sentences 2/3/4 e conclusion |
| provenance | PMID claim-linked, abstract indexed; full text unavailable |

Questa claim è diagnostic evidence con supporto PARTIAL_SUPPORT: il testo
locale tratta la prevalenza delle fusioni FGFR2 come gruppo e non dimostra in
modo separato la prevalenza/utilità della sola fusione AHCYL1. Anche qui non
è supportata una classificazione companion diagnostic.

## Campi mancanti comuni

Entrambe le claim non hanno diagnostic_id, device/test name, categoria
companion/complementary, terapia associata, tecnologia del device, stato
regolatorio, giurisdizione o un locator full-text. Il parent ha
original_intervention_associations vuoto; la pubblicazione collegata non è
quindi una terapia associata.

La distinzione applicata è:

    publication linked != claim supported
    diagnostic evidence != companion diagnostic
    test associato a una terapia != prova dell'efficacia della terapia
