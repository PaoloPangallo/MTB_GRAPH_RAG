# Author review pack — AI-assisted paper pre-annotations

This document is for author review of AI_DRAFT annotations. It is not final gold. The author must decide independently whether to confirm or override each draft.

## Consistency rules for author review

- **FULL_SUPPORT**: all semantically necessary elements of the candidate are documented.
- **PARTIAL_SUPPORT**: the core relation is documented, but a secondary specificity is missing (for example, a specific variant or disease subtype).
- **NO_SUPPORT**: the document discusses a related context but does not support the specific core relation.
- **CONTRADICTORY**: the document explicitly states the opposite of the candidate.
- **UNVERIFIABLE**: the frozen material is insufficient for a reasoned decision.

Important: if the polarity that defines the relation does not match or is missing (for example sensitivity versus resistance, or Supports versus Does Not Support), do not classify it automatically as PARTIAL_SUPPORT merely because gene or disease context coincide.

## Review order

High-priority cases first, then medium, then low. Sample identifiers remain unchanged.

## PAPER-05

Review priority: **HIGH**

### Candidate

- candidate_id: `GCA-ffc4f3959a383c945a0f1cc5`
- disease: `Prostate Cancer`
- subject: `Overexpression`
- predicate: `has_evidence_statement`
- object: `414`
- direction: `Supports`
- evidence_type: `Predictive`

### Source

- PMID: `25670080`
- PMCID: `PMC2538883`
- document type: `PUBMED_ABSTRACT`
- title: A targetable GATA2-IGF2 axis confers aggressiveness in lethal prostate cancer.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **HIGH**

### Evidence used by AI draft

- SourceUnit IDs: `SU-5fe2352856aefa860bcc5b3f`
- Literal quote: We used experimental models and clinical databases to identify GATA2 as a regulator of chemotherapy resistance and tumorigenicity in this context.

### Reasoning

The source documents a predictive/aggressiveness context in lethal prostate cancer and describes molecular upregulation, but the candidate subject is only the unspecific label Overexpression and does not identify the molecular entity. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-08

Review priority: **HIGH**

### Candidate

- candidate_id: `GCA-ffdedde41ece1506673a5c0e`
- disease: `Head And Neck Squamous Cell Carcinoma`
- subject: `High`
- predicate: `has_evidence_statement`
- object: `12850`
- direction: `Supports`
- evidence_type: `Predictive`

### Source

- PMID: `36806911`
- PMCID: `PMC8190047`
- document type: `PMC_FULLTEXT`
- title: On-treatment immune prognostic score for patients with relapsed and/or metastatic head and neck squamous cell carcinoma treated with immunotherapy

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **HIGH**

### Evidence used by AI draft

- SourceUnit IDs: `SU-312c39511ce92a06d5bddd85`
- Literal quote: NLR and fibrinogen levels are simple, inexpensive and readily available biomarkers that could be incorporated into an on-treatment scoring system and used to help predict survival and response to ICI in patients with R/M HNSCC.

### Reasoning

The source supports a high/low biomarker-based predictive relation in the stated disease context, but the candidate subject is the unqualified label High and does not identify the measured biomarker. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-12

Review priority: **HIGH**

### Candidate

- candidate_id: `GCA-ffbb1b3be5bd7e74024e8a2f`
- disease: `Childhood Acute Lymphocytic Leukemia`
- subject: `R238W`
- predicate: `has_evidence_statement`
- object: `7863`
- direction: `Supports`
- evidence_type: `Prognostic`

### Source

- PMID: `23377183`
- PMCID: `PMC2855889`
- document type: `PMC_FULLTEXT`
- title: A method and server for predicting damaging missense mutations

### AI draft fields

- disease: `NO`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NOT_APPLICABLE`
- direction: `NO`
- evidence_type: `NO`

AI overall draft: **UNVERIFIABLE**

Uncertainty: **HIGH**

### Evidence used by AI draft

- SourceUnit IDs: `SU-d79ac777bedabbc801f68620`
- Literal quote: A method and server for predicting damaging missense mutations

### Reasoning

The frozen SourceUnit bundle contains only the title and a supplementary-material label. It does not provide enough frozen document content to make a motivated judgement about R238W, childhood ALL, or a prognostic relation. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-14

Review priority: **HIGH**

### Candidate

- candidate_id: `GCA-fc343592a215c4ac9c9a1c43`
- disease: `Cancer`
- subject: `DPYD*13 HOMOZYGOSITY`
- predicate: `associated_with_sensitivity_to`
- object: `FLUOROURACIL`
- direction: `Adverse Response`
- evidence_type: `Predictive`

### Source

- PMID: `23988873`
- PMCID: `PMC2362417`
- document type: `PMC_FULLTEXT`
- title: Dihydropyrimidine dehydrogenase deficiency and fluorouracil-related toxicity

### AI draft fields

- disease: `NOT_APPLICABLE`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `YES`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **UNVERIFIABLE**

Uncertainty: **HIGH**

### Evidence used by AI draft

- SourceUnit IDs: `SU-42c7228f99e6048599039c05`
- Literal quote: Dihydropyrimidine dehydrogenase deficiency and fluorouracil-related toxicity

### Reasoning

The frozen SourceUnit bundle contains only the title. It names a broad fluorouracil-toxicity topic but cannot establish the candidate DPYD*13 homozygosity, cancer context, or the required specificity. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-01

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-eed9f53846f3cc651e23a469`
- disease: `Sertoli-Leydig Cell Tumor`
- subject: `D1709N`
- predicate: `has_evidence_statement`
- object: `5534`
- direction: `Does Not Support`
- evidence_type: `Diagnostic`

### Source

- PMID: `26428316`
- PMCID: `PMC3459463`
- document type: `PUBMED_ABSTRACT`
- title: A survey of DICER1 hotspot mutations in ovarian and testicular sex cord-stromal tumors.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NOT_APPLICABLE`
- direction: `NO`
- evidence_type: `NO`

AI overall draft: **NO_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-e85dc884b6309265871d65d9`
- Literal quote: Sertoli-Leydig cell tumors are characterized by the presence of somatic DICER1 hotspot mutations.

### Reasoning

The frozen abstract covers the disease and DICER1 hotspot mutations generally, but it does not document the candidate alteration D1709N or a diagnostic ‘Does Not Support’ relation. The candidate has no explicit gene field.

### Review flag

General DICER1/disease context is present, but the specific D1709N alteration and Does Not Support polarity must be evaluated as part of the candidate's semantic core.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-02

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-ffe78f2cb067426d4baf225d`
- disease: `Hematologic Cancer`
- subject: `Fusion`
- predicate: `has_evidence_statement`
- object: `1436`
- direction: `Supports`
- evidence_type: `Diagnostic`

### Source

- PMID: `27069254`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: The 2016 revision to the World Health Organization classification of myeloid neoplasms and acute leukemia.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-23b4c112b4ef9a4ecd7ef0a1`
- Literal quote: Since then, there have been numerous advances in the identification of unique biomarkers associated with some myeloid neoplasms and acute leukemias, largely derived from gene expression analysis and next-generation sequencing that can significantly improve the diagnostic criteria as well as the prognostic relevance of entities currently included in the WHO classification and that also suggest new entities that should be added.

### Reasoning

The source supports diagnostic biomarker work in hematologic malignancies in general, but the frozen candidate’s Fusion subject is not identified in the document. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-03

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-ffb6a639dda7e2af9dc154e0`
- disease: `Von Hippel-Lindau Disease`
- subject: `H191FS (c.571delC)`
- predicate: `has_evidence_statement`
- object: `5275`
- direction: `Supports`
- evidence_type: `Predisposing`

### Source

- PMID: `9829912`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: Germline mutation profile of the VHL gene in von Hippel-Lindau disease and in sporadic hemangioblastoma.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-792f163154f2bcd416b3533f`
- Literal quote: The disease has been associated with mutations of the VHL gene.

### Reasoning

The source supports the VHL-disease and mutation context, including a predisposing disease description, but does not identify the candidate H191FS (c.571delC) alteration. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-06

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-ffcd72c534472ec5090eea1f`
- disease: `Ovarian Cancer`
- subject: `V211L`
- predicate: `has_evidence_statement`
- object: `2882`
- direction: `Supports`
- evidence_type: `Predictive`

### Source

- PMID: `27908594`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: Rucaparib in relapsed, platinum-sensitive high-grade ovarian carcinoma (ARIEL2 Part 1): an international, multicentre, open-label, phase 2 trial.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-3c757ed1dee2a9a826ea5abd`
- Literal quote: In ARIEL2, we assessed the ability of tumour genomic LOH, quantified with a next-generation sequencing assay, to predict response to rucaparib, an oral PARP inhibitor.

### Reasoning

The source supports a predictive biomarker relation in ovarian carcinoma, but it does not identify the candidate V211L alteration. The candidate is an evidence statement without a drug field and has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-09

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-ffe5c124fb0b3bb1335a4014`
- disease: `Lung Adenocarcinoma`
- subject: `Fusion`
- predicate: `associated_with_sensitivity_to`
- object: `CRIZOTINIB`
- direction: `Sensitivity/Response`
- evidence_type: `Predictive`

### Source

- PMID: `20979473`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: EML4-ALK mutations in lung cancer that confer resistance to ALK inhibitors.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `NO`
- direction: `NO`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-3c966e52e24515bed27bcd81`
- Literal quote: The EML4 (echinoderm microtubule-associated protein-like 4)-ALK (anaplastic lymphoma kinase) fusion-type tyrosine kinase is an oncoprotein found in 4 to 5% of non-small-cell lung cancers, and clinical trials of specific inhibitors of ALK for the treatment of such tumors are currently under way.

### Reasoning

The source supports a fusion context in lung cancer but does not name crizotinib and describes resistance caused by secondary mutations rather than the candidate Fusion-to-crizotinib sensitivity relation. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-13

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-e7edb50600fc5996b63b35e4`
- disease: `B-lymphoblastic Leukemia/lymphoma`
- subject: `Fusion`
- predicate: `associated_with_sensitivity_to`
- object: `DASATINIB`
- direction: `Reduced Sensitivity`
- evidence_type: `Predictive`

### Source

- PMID: `21863287`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: RCSD1-ABL1-positive B lymphoblastic leukemia is sensitive to dexamethasone and tyrosine kinase inhibitors and rapidly evolves clonally by chromosomal translocations.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `YES`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **FULL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-e6cd8f8c4b8dfe535c1f34e4`
- Literal quote: Tyrosine kinase inhibitors, imatinib and dasatinib, coadministered with dexamethasone achieved transient clinical effects in the present RCSD1-ABL1-positive ALL. However, leukemic cells rapidly became refractory to this treatment following the subsequent development of three additional reciprocal chromosomal translocations, t(5;16)(q33;q24), dic(18;20)(p11.

### Reasoning

The source explicitly identifies the fusion and disease, includes dasatinib, and reports transient effects followed by refractoriness, supporting the candidate’s reduced-sensitivity relation. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-15

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-ff97755cefae20a730170d54`
- disease: `Melanoma`
- subject: `V600E`
- predicate: `associated_with_resistance_to`
- object: `TRAMETINIB`
- direction: `Resistance`
- evidence_type: `Predictive`

### Source

- PMID: `24576830`
- PMCID: `PMC3606893`
- document type: `PMC_FULLTEXT`
- title: A genome-scale RNA interference screen implicates NF1 loss in resistance to RAF inhibition

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `YES`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-d15474b67cf73a3ab49e3751`
- Literal quote: Characterization of surviving cells identified inactivation of NF1 as a novel mechanism of resistance to both B-RAF and MEK inhibition.

### Reasoning

The source covers B-RAFV600E melanoma, trametinib/MEK-inhibitor context, and resistance, but identifies NF1 inactivation rather than V600E as the resistance mechanism. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-16

Review priority: **MEDIUM**

### Candidate

- candidate_id: `GCA-fff906074758e0ee48366a8d`
- disease: `Chronic Myeloid Leukemia`
- subject: `T315I`
- predicate: `associated_with_resistance_to`
- object: `NILOTINIB`
- direction: `Resistance`
- evidence_type: `Predictive`

### Source

- PMID: `16772610`
- PMCID: `PMC552942`
- document type: `PUBMED_ABSTRACT`
- title: Comparison of imatinib mesylate, dasatinib (BMS-354825), and nilotinib (AMN107) in an N-ethyl-N-nitrosourea (ENU)-based mutagenesis screen: high efficacy of drug combinations.

### AI draft fields

- disease: `NO`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `YES`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **PARTIAL_SUPPORT**

Uncertainty: **MEDIUM**

### Evidence used by AI draft

- SourceUnit IDs: `SU-6468f4e0e5a568490fd4a917`
- Literal quote: BMS-354825 (dasatinib) and AMN107 (nilotinib) are potent alternate Abl inhibitors with activity against many imatinib mesylate-resistant BCR-ABL kinase domain (KD) mutants, except T315I.

### Reasoning

The frozen abstract directly supports T315I-associated resistance to nilotinib, but the supplied abstract does not explicitly state the candidate chronic myeloid leukemia disease context. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-04

Review priority: **LOW**

### Candidate

- candidate_id: `GCA-ffd2ba40df921cebf9d31e1a`
- disease: `Merkel Cell Carcinoma`
- subject: `Expression`
- predicate: `has_evidence_statement`
- object: `1578`
- direction: `Does Not Support`
- evidence_type: `Predictive`

### Source

- PMID: `27093365`
- PMCID: `PMC3919509`
- document type: `PMC_FULLTEXT`
- title: Mutational heterogeneity in cancer and the search for new cancer genes

### AI draft fields

- disease: `NO`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NOT_APPLICABLE`
- direction: `NO`
- evidence_type: `NO`

AI overall draft: **NO_SUPPORT**

Uncertainty: **LOW**

### Evidence used by AI draft

- SourceUnit IDs: `SU-31407ded3df9c7f9488fab7a`
- Literal quote: The first factor is gene expression level.

### Reasoning

The cited full text discusses mutation heterogeneity and expression across cancers, not Merkel cell carcinoma or a predictive ‘Does Not Support’ assertion for the candidate Expression subject. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-07

Review priority: **LOW**

### Candidate

- candidate_id: `GCA-ffd6d386640e05d3b78a3031`
- disease: `Acute Myeloid Leukemia`
- subject: `N822K`
- predicate: `associated_with_sensitivity_to`
- object: `SORAFENIB`
- direction: `Sensitivity/Response`
- evidence_type: `Predictive`

### Source

- PMID: `21482694`
- PMCID: `PMC2673122`
- document type: `PUBMED_ABSTRACT`
- title: Potent activity of ponatinib (AP24534) in models of FLT3-driven acute myeloid leukemia and other hematologic malignancies.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `NO`
- drug: `NO`
- direction: `NO`
- evidence_type: `NO`

AI overall draft: **NO_SUPPORT**

Uncertainty: **LOW**

### Evidence used by AI draft

- SourceUnit IDs: `SU-4948d2223db0812e37ff8a20`
- Literal quote: The activity of ponatinib against the FLT3-ITD mutant, found in up to 30% of acute myeloid leukemia (AML) patients, was particularly notable.

### Reasoning

The source concerns FLT3-ITD and ponatinib in AML, not the candidate N822K alteration or sorafenib. It therefore does not support the specific sensitivity relation. The candidate has no explicit gene field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-10

Review priority: **LOW**

### Candidate

- candidate_id: `GCA-fff42a22261e97c1160749e9`
- disease: `Lung Non-small Cell Carcinoma`
- subject: `T790M`
- predicate: `has_evidence_statement`
- object: `646`
- direction: `Supports`
- evidence_type: `Predictive`

### Source

- PMID: `25923550`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: Rociletinib in EGFR-mutated non-small-cell lung cancer.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **FULL_SUPPORT**

Uncertainty: **LOW**

### Evidence used by AI draft

- SourceUnit IDs: `SU-09079680a810c5e7169d5e55`
- Literal quote: Rociletinib was active in patients with EGFR-mutated NSCLC associated with the T790M resistance mutation.

### Reasoning

The frozen abstract explicitly connects T790M-mutated NSCLC with therapeutic activity, matching the candidate’s disease, alteration, supportive direction, and predictive evidence type. The candidate has no explicit gene or drug field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=

## PAPER-11

Review priority: **LOW**

### Candidate

- candidate_id: `GCA-ff6bdc720cc1fcd9134bf399`
- disease: `Acute Myeloid Leukemia`
- subject: `R132`
- predicate: `has_evidence_statement`
- object: `323`
- direction: `Does Not Support`
- evidence_type: `Prognostic`

### Source

- PMID: `20368538`
- PMCID: `NOT_AVAILABLE`
- document type: `PUBMED_ABSTRACT`
- title: Impact of IDH1 R132 mutations and an IDH1 single nucleotide polymorphism in cytogenetically normal acute myeloid leukemia: SNP rs11554137 is an adverse prognostic factor.

### AI draft fields

- disease: `YES`
- gene: `NOT_APPLICABLE`
- alteration: `YES`
- drug: `NOT_APPLICABLE`
- direction: `YES`
- evidence_type: `YES`

AI overall draft: **FULL_SUPPORT**

Uncertainty: **LOW**

### Evidence used by AI draft

- SourceUnit IDs: `SU-b6b3e32524c246e386d66f09`
- Literal quote: IDH1 R132 mutations had no impact on prognosis.

### Reasoning

The frozen abstract directly states the candidate’s negative prognostic relation for R132 mutations in AML. The candidate has no explicit gene or drug field.

### Author decision

AUTHOR_DECISION=
CONFIRM | OVERRIDE | PENDING

AUTHOR_FINAL_LABEL=
FULL_SUPPORT | PARTIAL_SUPPORT | NO_SUPPORT | CONTRADICTORY | UNVERIFIABLE | PENDING

AUTHOR_NOTES=
