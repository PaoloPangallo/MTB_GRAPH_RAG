"""Gli otto profili clinici di fonte, da annotazione umana.

Provenienza
-----------
Ogni campo deriva dai dati **gia' annotati a mano** nel pilota v1: il campo
`relevant_population_or_rule` del manifest delle fonti e i `mandatory_qualifiers`
delle claim. Nessun modello linguistico ha generato o completato questi profili, ed
e' un requisito del protocollo: sono lo strumento con cui si misura se un modello
conserva i qualificatori, quindi non possono venire da un modello.

Perche' esistono
----------------
Il grafo non modella linea di terapia, setting, stadio, resezione, terapie
precedenti, popolazione, completezza del regime ne' prerequisiti di biomarcatore.
Senza questi profili, l'applicabilita' di una fonte al caso non e' verificabile:
si potrebbe solo constatare che il PMID coincide, che e' precisamente il tipo di
corrispondenza superficiale che il protocollo vieta.

Stato
-----
Tutti `human_reviewed`, versione `human_reviewed_v1`. **Non** `frozen`: il freeze
richiede la seconda revisione indipendente, ancora aperta.
"""

from __future__ import annotations

from .contracts import HUMAN_REVIEWED, SourceClinicalProfile

_REVIEWER = "annotatore_1"
_VERSION = "human_reviewed_v1"
_CREATED = "2026-07-21"
_METHOD = "human_annotation_from_pilot_v1_source_manifest"


def _profile(**kwargs) -> SourceClinicalProfile:
    return SourceClinicalProfile(
        extraction_method=_METHOD,
        extractor_version=_VERSION,
        review_status=HUMAN_REVIEWED,
        reviewer=_REVIEWER,
        created_at=_CREATED,
        **kwargs,
    )


REVIEWED_PROFILES: tuple[SourceClinicalProfile, ...] = (
    _profile(
        source_id="S-K1-1",
        pmid="32203698",
        nct_ids=("NCT02924376",),
        title="Pemigatinib FIGHT-202",
        disease="cholangiocarcinoma",
        population="Previously treated locally advanced/metastatic or surgically "
        "unresectable cholangiocarcinoma with FGFR2 fusion or rearrangement",
        stage="locally advanced or metastatic; surgically unresectable",
        setting="advanced/metastatic, previously treated",
        therapy_line="second line or later",
        prior_therapies=("at least one prior systemic treatment",),
        biomarker_requirements=("FGFR2 fusion or rearrangement",),
        regimen="pemigatinib monotherapy",
        interventions=("pemigatinib",),
        inclusion_criteria_summary="Progression after at least one prior treatment; ECOG 0-2",
        exclusion_criteria_summary="Prior selective FGFR inhibitor excluded",
        source_spans=(
            "Previously treated locally advanced/metastatic CCA; FGFR2 "
            "fusion/rearrangement; NCT02924376",
            "Progression after >=1 systemic line; ECOG 0-2; prior selective FGFR "
            "inhibitor excluded",
        ),
        confidence="high",
    ),
    _profile(
        source_id="S-K1-3",
        pmid="36652354",
        nct_ids=("NCT02052778",),
        title="Futibatinib FOENIX-CCA2",
        disease="intrahepatic cholangiocarcinoma",
        population="Unresectable or metastatic intrahepatic cholangiocarcinoma with "
        "FGFR2 fusion or rearrangement, previously treated",
        stage="unresectable or metastatic",
        setting="advanced/metastatic, previously treated",
        therapy_line="second line or later",
        prior_therapies=("at least one prior systemic line",),
        biomarker_requirements=("FGFR2 fusion or rearrangement",),
        regimen="futibatinib monotherapy",
        interventions=("futibatinib",),
        inclusion_criteria_summary="Unresectable/metastatic iCCA after prior systemic therapy",
        exclusion_criteria_summary="Prior FGFR inhibitors excluded",
        source_spans=(
            "Unresectable/metastatic iCCA; prior systemic therapy; prior FGFR "
            "inhibitors excluded",
            "FGFR2 rearranged iCCA cohort; futibatinib",
        ),
        confidence="high",
    ),
    _profile(
        source_id="S-A2-1",
        pmid="27432227",
        nct_ids=(),
        title="Resistance to first/second-generation ALK inhibitors",
        disease="ALK-positive non-small cell lung cancer",
        population="Advanced ALK-positive NSCLC progressing after ALK inhibition",
        stage="advanced",
        setting="post-progression on ALK inhibitor",
        therapy_line="after first or second generation ALK TKI",
        prior_therapies=("first-generation ALK TKI", "second-generation ALK TKI"),
        biomarker_requirements=("ALK rearrangement", "ALK kinase domain mutation"),
        regimen="translational study, no single regimen",
        interventions=(),
        inclusion_criteria_summary="Biopsies after progression on ALK inhibitors",
        exclusion_criteria_summary="",
        source_spans=(
            "G1202R frequency increases after second-generation agents; mutation "
            "context predicts lorlatinib sensitivity in models",
        ),
        confidence="medium",
    ),
    _profile(
        source_id="S-A2-2",
        pmid="30892989",
        nct_ids=("NCT01970865",),
        title="ALK resistance mutations and lorlatinib efficacy",
        disease="ALK-positive non-small cell lung cancer",
        population="Pretreated advanced ALK-positive NSCLC, including carriers of "
        "G1202R/del",
        stage="advanced",
        setting="pretreated advanced disease",
        therapy_line="second line or later",
        prior_therapies=("at least one prior ALK TKI",),
        biomarker_requirements=(
            "ALK rearrangement",
            "ALK mutation detected in plasma or tissue",
        ),
        regimen="lorlatinib monotherapy",
        interventions=("lorlatinib",),
        inclusion_criteria_summary="Pretreated advanced ALK+ NSCLC with ALK mutation "
        "detected in plasma or tissue",
        exclusion_criteria_summary="",
        source_spans=(
            "Pretreated advanced ALK+ NSCLC; clinical activity among G1202R/del carriers",
            "Advanced ALK/ROS1-positive NSCLC; pretreated cohorts",
        ),
        confidence="high",
    ),
    _profile(
        source_id="S-A2-4",
        pmid="29650534",
        nct_ids=(),
        title="Compound ALK mutations and lorlatinib resistance",
        disease="ALK-positive lung cancer",
        population="Patients developing compound ALK kinase-domain mutations during "
        "sequential ALK inhibition",
        stage="advanced",
        setting="post-progression after sequential ALK inhibition",
        therapy_line="third line or later",
        prior_therapies=("sequential ALK TKI therapy including lorlatinib",),
        biomarker_requirements=(
            "ALK rearrangement",
            "compound ALK kinase-domain mutation, e.g. G1202R/L1196M",
        ),
        regimen="translational and clinical study",
        interventions=("lorlatinib",),
        inclusion_criteria_summary="Compound mutations selected during sequential ALK "
        "inhibition",
        exclusion_criteria_summary="Single ALK resistance mutation is a different "
        "population and is not covered by this source",
        source_spans=(
            "Compound mutations such as G1202R/L1196M can emerge after sequential "
            "treatment",
        ),
        confidence="high",
    ),
    _profile(
        source_id="S-C1-1",
        pmid="29151359",
        nct_ids=("NCT02296125",),
        title="FLAURA primary analysis",
        disease="advanced non-small cell lung cancer",
        population="Previously untreated advanced EGFR-mutated NSCLC with Ex19del or "
        "L858R",
        stage="locally advanced or metastatic",
        setting="first-line advanced/metastatic",
        therapy_line="first line",
        prior_therapies=(),
        biomarker_requirements=("EGFR exon 19 deletion or L858R",),
        regimen="osimertinib monotherapy versus comparator EGFR-TKI",
        interventions=("osimertinib",),
        inclusion_criteria_summary="Locally advanced or metastatic, treatment-naive, "
        "eligible for first-line EGFR-TKI",
        exclusion_criteria_summary="Prior systemic therapy for advanced disease excluded",
        source_spans=(
            "Previously untreated advanced NSCLC; Ex19del/L858R; first-line",
            "Locally advanced/metastatic, treatment-naive, first-line EGFR-TKI eligible",
        ),
        confidence="high",
    ),
    _profile(
        source_id="S-C1-3",
        pmid="32955177",
        nct_ids=("NCT02511106",),
        title="ADAURA primary analysis",
        disease="completely resected stage IB-IIIA non-small cell lung cancer",
        population="Completely resected stage IB-IIIA EGFR-mutated NSCLC",
        stage="IB-IIIA, completely resected",
        setting="adjuvant after complete resection",
        therapy_line="adjuvant",
        prior_therapies=("complete surgical resection", "adjuvant chemotherapy optional"),
        biomarker_requirements=("EGFR exon 19 deletion or L858R",),
        regimen="adjuvant osimertinib versus placebo",
        interventions=("osimertinib",),
        inclusion_criteria_summary="Complete resection; stage IB-IIIA; with or without "
        "adjuvant chemotherapy",
        exclusion_criteria_summary="Unresected, locally advanced or metastatic disease "
        "is a different population and is not covered by this source",
        source_spans=(
            "Completely resected stage IB-IIIA; adjuvant setting",
            "Complete resection; stage IB-IIIA; adjuvant",
        ),
        confidence="high",
    ),
    _profile(
        source_id="S-C1-5",
        pmid="27959700",
        nct_ids=("NCT02151981",),
        title="AURA3",
        disease="advanced non-small cell lung cancer",
        population="T790M-positive advanced NSCLC after progression on first-line "
        "EGFR-TKI",
        stage="advanced",
        setting="post-progression, T790M-positive",
        therapy_line="second line",
        prior_therapies=("first-line EGFR-TKI with subsequent progression",),
        biomarker_requirements=("EGFR T790M",),
        regimen="osimertinib versus platinum-pemetrexed",
        interventions=("osimertinib",),
        inclusion_criteria_summary="T790M-positive advanced NSCLC after progression on "
        "first-line EGFR-TKI",
        exclusion_criteria_summary="Treatment-naive disease and T790M-negative disease "
        "are different populations and are not covered by this source",
        source_spans=(
            "T790M-positive advanced NSCLC after progression on first-line EGFR-TKI",
            "Post-progression; prior EGFR-TKI; T790M-positive",
        ),
        confidence="high",
    ),
)

# I PMID che il protocollo richiede di coprire.
REQUIRED_PMIDS = (
    "32203698",
    "36652354",
    "27432227",
    "30892989",
    "29650534",
    "29151359",
    "32955177",
    "27959700",
)
