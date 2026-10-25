Pilot claim provenance
=======================

Le etichette di bucket provengono dagli output esplorativi manuali gia presenti in benchmarks/mtb_evidence/exploratory/manual_v3_cases_product_hardening/. I bucket non sono attributi delle claim nel repository.

## primary FGFR2 ? CLM-1d3ba8b6ae49232969c7

Claim: therapeutic / atomic_intervention_claim / pending_verification

Biomarker: FGFR2::v Fusion OR FGFR2::? Fusion; disease: Intrahepatic Cholangiocarcinoma; intervention: derazantinib; direction: sensitivity

Parent: GEP-a49c49f450628b94e307; parent graph evidence: evidence:7329; graph evidence: evidence:7329

Source unit: null; graph node id: null; source ids claim: null; source ids parent: PUBMED:30420614

PMID: null; DOI: null; NCT: null; URL: null

Locator: null

Bucket reference: case_01_api_response.json:primary

Provenance: PARENT_ONLY; first missing link: PARENT_TO_SOURCE_UNIT; diagnosis: DATA_PRESENT_BUT_NOT_PROPAGATED; confidence: MEDIUM

A claim-parent: PRESENT; B parent-source unit: MISSING; C source unit-original: MISSING; D original-identifier: PRESENT; E identifier-locator/text: MISSING

Note: parent_source_ids e source_record_ids presenti, source_unit_ids e locators mancanti nella claim; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente

## primary ALK G1202R ? CLM-0f234bc9c53847910521

Claim: therapeutic / atomic_intervention_claim / pending_verification

Biomarker: ALK G1202R AND v::ALK Fusion; disease: Non-Small Cell Lung Cancer; intervention: alectinib hydrochloride; direction: resistance

Parent: GEP-e85a4cca147f64591ac6; parent graph evidence: evidence:100002; graph evidence: evidence:100002

Source unit: null; graph node id: null; source ids claim: null; source ids parent: PUBMED:24736079;PUBMED:27130468;PUBMED:27432227;PUBMED:29373100;PUBMED:29376144;PUBMED:29650534

PMID: null; DOI: null; NCT: null; URL: null

Locator: null

Bucket reference: case_02_api_response.json:primary

Provenance: PARENT_ONLY; first missing link: PARENT_TO_SOURCE_UNIT; diagnosis: DATA_PRESENT_BUT_NOT_PROPAGATED; confidence: MEDIUM

A claim-parent: PRESENT; B parent-source unit: MISSING; C source unit-original: MISSING; D original-identifier: PRESENT; E identifier-locator/text: MISSING

Note: parent_source_ids e source_record_ids presenti, source_unit_ids e locators mancanti nella claim; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente

## primary EGFR/osimertinib ? CLM-1ee5f9a16a678cebf993

Claim: therapeutic / atomic_intervention_claim / pending_verification

Biomarker: EGFR L858R; disease: Lung Non-small Cell Carcinoma; intervention: osimertinib; direction: sensitivity

Parent: GEP-d1fd81616ff16e60d884; parent graph evidence: evidence:4294; graph evidence: evidence:4294

Source unit: null; graph node id: null; source ids claim: null; source ids parent: PUBMED:24893891

PMID: null; DOI: null; NCT: null; URL: null

Locator: null

Bucket reference: case_03_api_response.json:primary

Provenance: PARENT_ONLY; first missing link: PARENT_TO_SOURCE_UNIT; diagnosis: DATA_PRESENT_BUT_NOT_PROPAGATED; confidence: MEDIUM

A claim-parent: PRESENT; B parent-source unit: MISSING; C source unit-original: MISSING; D original-identifier: PRESENT; E identifier-locator/text: MISSING

Note: parent_source_ids e source_record_ids presenti, source_unit_ids e locators mancanti nella claim; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente

## audit aggregate EGFR ? CLM-4ffe85304f3ef5533b58

Claim: therapeutic / aggregate_intervention_claim / adjudicated

Biomarker: EGFR L858R; disease: Lung Non-small Cell Carcinoma; intervention: egfr tyrosine kinase inhibitor; direction: sensitivity

Parent: GEP-4be33662c8244659895a; parent graph evidence: evidence:275; graph evidence: evidence:275

Source unit: SU-24457318-cohort-egfr-tki; graph node id: null; source ids claim: PMID:24457318; source ids parent: PUBMED:24457318

PMID: PMID:24457318; DOI: null; NCT: null; URL: null

Locator: [{"source_id":"PMID:24457318","text":"abstract, coorte retrospettiva di 70 pazienti trattati con EGFR-TKI"}]

Bucket reference: case_03_api_response.json:audit

Provenance: VERIFIED_LOCATOR; first missing link: NONE; diagnosis: NONE_OBSERVED; confidence: HIGH

A claim-parent: PRESENT; B parent-source unit: PRESENT; C source unit-original: PRESENT; D original-identifier: PRESENT; E identifier-locator/text: PRESENT

Note: source_id e locator presenti sulla claim; parent usato solo come controllo; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente; source_unit_id presente anche in artefatti ausiliari review, non in un registro canonico runtime

## rejected aggregate FGFR2 ? CLM-90e863f00f134fc3cd3d

Claim: therapeutic / aggregate_intervention_claim / adjudicated

Biomarker: FGFR2::BICC1 Fusion; disease: Cholangiocarcinoma; intervention: infigratinib + pd173074; direction: sensitivity

Parent: GEP-d7085106bdd9a024ff4c; parent graph evidence: evidence:1851; graph evidence: evidence:1851

Source unit: SU-24122810-nih3t3-fgfr-inhibitor-assay; graph node id: null; source ids claim: PMID:24122810; source ids parent: PUBMED:24122810

PMID: PMID:24122810; DOI: null; NCT: null; URL: null

Locator: [{"source_id":"PMID:24122810","text":"abstract, enunciato finale sulla soppressione della trasformazione, cellule NIH3T3"}]

Bucket reference: case_03_api_response.json:rejected

Provenance: VERIFIED_LOCATOR; first missing link: NONE; diagnosis: NONE_OBSERVED; confidence: HIGH

A claim-parent: PRESENT; B parent-source unit: PRESENT; C source unit-original: PRESENT; D original-identifier: PRESENT; E identifier-locator/text: PRESENT

Note: source_id e locator presenti sulla claim; parent usato solo come controllo; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente; source_unit_id presente anche in artefatti ausiliari review, non in un registro canonico runtime

## aggregate FGFR2 ? CLM-5071bb2d8657ac0fbed0

Claim: therapeutic / aggregate_intervention_claim / adjudicated

Biomarker: FGFR2::AHCYL1 Fusion; disease: Cholangiocarcinoma; intervention: infigratinib + pd173074; direction: sensitivity

Parent: GEP-ee90f3e190e6ca617027; parent graph evidence: evidence:1853; graph evidence: evidence:1853

Source unit: SU-24122810-nih3t3-fgfr-inhibitor-assay; graph node id: null; source ids claim: PMID:24122810; source ids parent: PUBMED:24122810

PMID: PMID:24122810; DOI: null; NCT: null; URL: null

Locator: [{"source_id":"PMID:24122810","text":"abstract, enunciato finale sulla soppressione della trasformazione, cellule NIH3T3"}]

Bucket reference: case_01_api_response.json:rejected

Provenance: VERIFIED_LOCATOR; first missing link: NONE; diagnosis: NONE_OBSERVED; confidence: HIGH

A claim-parent: PRESENT; B parent-source unit: PRESENT; C source unit-original: PRESENT; D original-identifier: PRESENT; E identifier-locator/text: PRESENT

Note: source_id e locator presenti sulla claim; parent usato solo come controllo; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente; source_unit_id presente anche in artefatti ausiliari review, non in un registro canonico runtime

## claim without direct source ? CLM-1ee5f9a16a678cebf993

Claim: therapeutic / atomic_intervention_claim / pending_verification

Biomarker: EGFR L858R; disease: Lung Non-small Cell Carcinoma; intervention: osimertinib; direction: sensitivity

Parent: GEP-d1fd81616ff16e60d884; parent graph evidence: evidence:4294; graph evidence: evidence:4294

Source unit: null; graph node id: null; source ids claim: null; source ids parent: PUBMED:24893891

PMID: null; DOI: null; NCT: null; URL: null

Locator: null

Bucket reference: case_03_api_response.json:primary

Provenance: PARENT_ONLY; first missing link: PARENT_TO_SOURCE_UNIT; diagnosis: DATA_PRESENT_BUT_NOT_PROPAGATED; confidence: MEDIUM

A claim-parent: PRESENT; B parent-source unit: MISSING; C source unit-original: MISSING; D original-identifier: PRESENT; E identifier-locator/text: MISSING

Note: parent_source_ids e source_record_ids presenti, source_unit_ids e locators mancanti nella claim; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente

## best available provenance ? CLM-8941c177da91f66ff93a

Claim: diagnostic / diagnostic_claim / first_review_complete

Biomarker: FGFR2::BICC1 Fusion; disease: Intrahepatic Cholangiocarcinoma; intervention: ; direction: diagnostic

Parent: GEP-f73a180a63fd22932198; parent graph evidence: evidence:1846; graph evidence: evidence:1846

Source unit: PU-PMID-24122810-cohort-1; graph node id: null; source ids claim: PMID:24122810; source ids parent: PUBMED:24122810

PMID: PMID:24122810; DOI: null; NCT: null; URL: null

Locator: [{"abstract_sentence":2,"section":"UNLABELLED","source_id":"PMID:24122810"},{"abstract_sentence":3,"section":"UNLABELLED","source_id":"PMID:24122810"},{"abstract_sentence":4,"section":"UNLABELLED","source_id":"PMID:24122810"},{"abstract_sentence":0,"section":"CONCLUSION","source_id":"PMID:24122810"}]

Bucket reference: case_01_api_response.json:rejected

Provenance: VERIFIED_LOCATOR; first missing link: NONE; diagnosis: NONE_OBSERVED; confidence: HIGH

A claim-parent: PRESENT; B parent-source unit: PRESENT; C source unit-original: PRESENT; D original-identifier: PRESENT; E identifier-locator/text: PRESENT

Note: source_id e locator presenti sulla claim; parent usato solo come controllo; publication_title assente; source_type assente; graph_node_id assente; graph_evidence_id disponibile separatamente; source_unit_id presente anche in artefatti ausiliari review, non in un registro canonico runtime
