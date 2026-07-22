# Proposta strutturale — BA-aafcf903d25ff168

> Questa e' una **proposta automatica**, non una revisione. Respingerla e' un
> esito legittimo quanto accettarla.

## Fonte

- **PMID:** 22235099
- **Testo consultato:** full_text
- **Locator:** PMC3311875#full_text

## Struttura proposta

- **Stato:** `clinical_preclinical_split_required`
- **Verdetto del rilevatore:** `split_required`
- Bracci rilevati: 0 · modelli preclinici: 46 · comparatori: 1

la fonte contiene sia una componente clinica sia una preclinica.

## Unita' candidate

| Unita' | Tipo | Propagabile |
| --- | --- | --- |
| `PU-PMID-22235099-clinical-component` | `clinical_observational_cohort` | **no** |
| `PU-PMID-22235099-preclinical-component` | `preclinical_in_vitro` | **no** |

## Proposizioni

| statement | intervento | candidato | supporto |
| --- | --- | --- | --- |
| `ES-V2-evidence-4288` | crizotinib | `candidate_ambiguous` | `clinical_observation_with_preclinical_validation` |
| `ES-V2-evidence-764` | crizotinib | `candidate_ambiguous` | `clinical_observation_with_preclinical_validation` |
| `ES-V2-evidence-766` | crizotinib | `candidate_ambiguous` | `clinical_observation_with_preclinical_validation` |

## Da non propagare

- non propagare `population` fra componente clinica e preclinica
- non propagare `setting` fra componente clinica e preclinica
- non propagare `therapy_line` fra componente clinica e preclinica
- non propagare `stage` fra componente clinica e preclinica
- non propagare `comparator` fra componente clinica e preclinica

## Estratti

- **clinical.patients** — «…8/1078-0432.CCR-11-2906 NIHMS362229 NIHPA362229 1 Article Mechanisms of Resistance to Crizotinib in Patients with ALK Gene Rearranged Non-Small Cell Lung Cancer Doebele Robert C. 1 Pilling Amanda B. 1 Aisner…»
- **clinical.patients** — «…ng. It may also be used consistent with the principles of fair use under the copyright law. Purpose Patients with anaplastic lymphoma kinase ( ALK ) gene rearrangements often manifest dramatic responses to cr…»
- **clinical.patients** — «…manifest dramatic responses to crizotinib, a small molecule ALK inhibitor. Unfortunately, not every patient responds and acquired drug resistance inevitably develops in those that do respond. This study aime…»
- **clinical.patients** — «…define molecular mechanisms of resistance to crizotinib in ALK+ non-small cell lung cancer (NSCLC) patients. Experimental Design We analyzed tissue obtained from 14 ALK+ NSCLC patients demonstrating evidence…»
- **clinical.patients** — «…ll lung cancer (NSCLC) patients. Experimental Design We analyzed tissue obtained from 14 ALK+ NSCLC patients demonstrating evidence of radiologic progression while on crizotinib in order to define mechanisms…»
- **clinical.patients** — «…ib in order to define mechanisms of intrinsic and acquired resistance to crizotinib. Results Eleven patients had material evaluable for molecular analysis. Four patients (36%) developed secondary mutations in…»
- **clinical.patients** — «…sistance to crizotinib. Results Eleven patients had material evaluable for molecular analysis. Four patients (36%) developed secondary mutations in the tyrosine kinase domain of ALK . A novel mutation in the…»
- **clinical.patients** — «…titution that confers resistance to crizotinib in vitro , was identified in two of these cases. Two patients, one with a resistance mutation, exhibited new onset ALK copy number gain (CNG). One patient demons…»

## Domande al revisore

1. La fonte descrive davvero le unita' proposte, o la partizione e' un artefatto dei segnali lessicali?
2. Quali proposizioni appartengono a ciascuna unita'?
3. Quali dimensioni sono condivise fra le unita' e quali sono specifiche?
4. Esistono dimensioni che la fonte non permette di separare? Marcale `not_separable`, non `unknown`.
5. La proposta va accettata, modificata o respinta?

---

Questo pacchetto non contiene clinical gold, terapie attese, metriche della
pipeline, decisioni finali ne' l'esito del pacchetto gia' revisionato.

