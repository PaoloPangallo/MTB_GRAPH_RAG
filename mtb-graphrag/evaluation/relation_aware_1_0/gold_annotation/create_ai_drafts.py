"""Create review-required AI pre-annotation drafts from the frozen paper pack only.

This script deliberately reads only candidate.json, source_overview.md and
source_units.md.  It neither imports the runtime nor reads human annotation
forms, so the generated files remain independent of system outputs and of the
subsequent human primary/review annotations.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parent
DRAFT_ROOT = PACK_ROOT / "ai_drafts"


def draft(
    fields: tuple[str, str, str, str, str, str],
    overall: str,
    unit_ids: list[str],
    quote: str,
    reasoning: str,
    uncertainty: str,
) -> dict[str, object]:
    return {
        "fields": fields,
        "overall": overall,
        "unit_ids": unit_ids,
        "quote": quote,
        "reasoning": reasoning,
        "uncertainty": uncertainty,
    }


# These are draft judgements authored from the frozen candidate/source text.
# The candidate payload does not expose a gene field for these evidence-statement
# relations; gene agreement is therefore NOT_APPLICABLE rather than inferred.
DRAFTS = {
    "PAPER-01": draft(
        ("YES", "NOT_APPLICABLE", "NO", "NOT_APPLICABLE", "NO", "NO"),
        "NO_SUPPORT",
        ["SU-e85dc884b6309265871d65d9"],
        "Sertoli-Leydig cell tumors are characterized by the presence of somatic DICER1 hotspot mutations.",
        "The frozen abstract covers the disease and DICER1 hotspot mutations generally, but it does not document the candidate alteration D1709N or a diagnostic ‘Does Not Support’ relation. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-02": draft(
        ("YES", "NOT_APPLICABLE", "NO", "NOT_APPLICABLE", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-23b4c112b4ef9a4ecd7ef0a1"],
        "Since then, there have been numerous advances in the identification of unique biomarkers associated with some myeloid neoplasms and acute leukemias, largely derived from gene expression analysis and next-generation sequencing that can significantly improve the diagnostic criteria as well as the prognostic relevance of entities currently included in the WHO classification and that also suggest new entities that should be added.",
        "The source supports diagnostic biomarker work in hematologic malignancies in general, but the frozen candidate’s Fusion subject is not identified in the document. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-03": draft(
        ("YES", "NOT_APPLICABLE", "NO", "NOT_APPLICABLE", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-792f163154f2bcd416b3533f"],
        "The disease has been associated with mutations of the VHL gene.",
        "The source supports the VHL-disease and mutation context, including a predisposing disease description, but does not identify the candidate H191FS (c.571delC) alteration. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-04": draft(
        ("NO", "NOT_APPLICABLE", "NO", "NOT_APPLICABLE", "NO", "NO"),
        "NO_SUPPORT",
        ["SU-31407ded3df9c7f9488fab7a"],
        "The first factor is gene expression level.",
        "The cited full text discusses mutation heterogeneity and expression across cancers, not Merkel cell carcinoma or a predictive ‘Does Not Support’ assertion for the candidate Expression subject. The candidate has no explicit gene field.",
        "LOW",
    ),
    "PAPER-05": draft(
        ("YES", "NOT_APPLICABLE", "YES", "NOT_APPLICABLE", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-5fe2352856aefa860bcc5b3f"],
        "We used experimental models and clinical databases to identify GATA2 as a regulator of chemotherapy resistance and tumorigenicity in this context.",
        "The source documents a predictive/aggressiveness context in lethal prostate cancer and describes molecular upregulation, but the candidate subject is only the unspecific label Overexpression and does not identify the molecular entity. The candidate has no explicit gene field.",
        "HIGH",
    ),
    "PAPER-06": draft(
        ("YES", "NOT_APPLICABLE", "NO", "NOT_APPLICABLE", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-3c757ed1dee2a9a826ea5abd"],
        "In ARIEL2, we assessed the ability of tumour genomic LOH, quantified with a next-generation sequencing assay, to predict response to rucaparib, an oral PARP inhibitor.",
        "The source supports a predictive biomarker relation in ovarian carcinoma, but it does not identify the candidate V211L alteration. The candidate is an evidence statement without a drug field and has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-07": draft(
        ("YES", "NOT_APPLICABLE", "NO", "NO", "NO", "NO"),
        "NO_SUPPORT",
        ["SU-4948d2223db0812e37ff8a20"],
        "The activity of ponatinib against the FLT3-ITD mutant, found in up to 30% of acute myeloid leukemia (AML) patients, was particularly notable.",
        "The source concerns FLT3-ITD and ponatinib in AML, not the candidate N822K alteration or sorafenib. It therefore does not support the specific sensitivity relation. The candidate has no explicit gene field.",
        "LOW",
    ),
    "PAPER-08": draft(
        ("YES", "NOT_APPLICABLE", "YES", "NOT_APPLICABLE", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-312c39511ce92a06d5bddd85"],
        "NLR and fibrinogen levels are simple, inexpensive and readily available biomarkers that could be incorporated into an on-treatment scoring system and used to help predict survival and response to ICI in patients with R/M HNSCC.",
        "The source supports a high/low biomarker-based predictive relation in the stated disease context, but the candidate subject is the unqualified label High and does not identify the measured biomarker. The candidate has no explicit gene field.",
        "HIGH",
    ),
    "PAPER-09": draft(
        ("YES", "NOT_APPLICABLE", "YES", "NO", "NO", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-3c966e52e24515bed27bcd81"],
        "The EML4 (echinoderm microtubule-associated protein-like 4)-ALK (anaplastic lymphoma kinase) fusion-type tyrosine kinase is an oncoprotein found in 4 to 5% of non-small-cell lung cancers, and clinical trials of specific inhibitors of ALK for the treatment of such tumors are currently under way.",
        "The source supports a fusion context in lung cancer but does not name crizotinib and describes resistance caused by secondary mutations rather than the candidate Fusion-to-crizotinib sensitivity relation. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-10": draft(
        ("YES", "NOT_APPLICABLE", "YES", "NOT_APPLICABLE", "YES", "YES"),
        "FULL_SUPPORT",
        ["SU-09079680a810c5e7169d5e55"],
        "Rociletinib was active in patients with EGFR-mutated NSCLC associated with the T790M resistance mutation.",
        "The frozen abstract explicitly connects T790M-mutated NSCLC with therapeutic activity, matching the candidate’s disease, alteration, supportive direction, and predictive evidence type. The candidate has no explicit gene or drug field.",
        "LOW",
    ),
    "PAPER-11": draft(
        ("YES", "NOT_APPLICABLE", "YES", "NOT_APPLICABLE", "YES", "YES"),
        "FULL_SUPPORT",
        ["SU-b6b3e32524c246e386d66f09"],
        "IDH1 R132 mutations had no impact on prognosis.",
        "The frozen abstract directly states the candidate’s negative prognostic relation for R132 mutations in AML. The candidate has no explicit gene or drug field.",
        "LOW",
    ),
    "PAPER-12": draft(
        ("NO", "NOT_APPLICABLE", "NO", "NOT_APPLICABLE", "NO", "NO"),
        "UNVERIFIABLE",
        ["SU-d79ac777bedabbc801f68620"],
        "A method and server for predicting damaging missense mutations",
        "The frozen SourceUnit bundle contains only the title and a supplementary-material label. It does not provide enough frozen document content to make a motivated judgement about R238W, childhood ALL, or a prognostic relation. The candidate has no explicit gene field.",
        "HIGH",
    ),
    "PAPER-13": draft(
        ("YES", "NOT_APPLICABLE", "YES", "YES", "YES", "YES"),
        "FULL_SUPPORT",
        ["SU-e6cd8f8c4b8dfe535c1f34e4"],
        "Tyrosine kinase inhibitors, imatinib and dasatinib, coadministered with dexamethasone achieved transient clinical effects in the present RCSD1-ABL1-positive ALL. However, leukemic cells rapidly became refractory to this treatment following the subsequent development of three additional reciprocal chromosomal translocations, t(5;16)(q33;q24), dic(18;20)(p11.",
        "The source explicitly identifies the fusion and disease, includes dasatinib, and reports transient effects followed by refractoriness, supporting the candidate’s reduced-sensitivity relation. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-14": draft(
        ("NOT_APPLICABLE", "NOT_APPLICABLE", "NO", "YES", "YES", "YES"),
        "UNVERIFIABLE",
        ["SU-42c7228f99e6048599039c05"],
        "Dihydropyrimidine dehydrogenase deficiency and fluorouracil-related toxicity",
        "The frozen SourceUnit bundle contains only the title. It names a broad fluorouracil-toxicity topic but cannot establish the candidate DPYD*13 homozygosity, cancer context, or the required specificity. The candidate has no explicit gene field.",
        "HIGH",
    ),
    "PAPER-15": draft(
        ("YES", "NOT_APPLICABLE", "YES", "YES", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-d15474b67cf73a3ab49e3751"],
        "Characterization of surviving cells identified inactivation of NF1 as a novel mechanism of resistance to both B-RAF and MEK inhibition.",
        "The source covers B-RAFV600E melanoma, trametinib/MEK-inhibitor context, and resistance, but identifies NF1 inactivation rather than V600E as the resistance mechanism. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
    "PAPER-16": draft(
        ("NO", "NOT_APPLICABLE", "YES", "YES", "YES", "YES"),
        "PARTIAL_SUPPORT",
        ["SU-6468f4e0e5a568490fd4a917"],
        "BMS-354825 (dasatinib) and AMN107 (nilotinib) are potent alternate Abl inhibitors with activity against many imatinib mesylate-resistant BCR-ABL kinase domain (KD) mutants, except T315I.",
        "The frozen abstract directly supports T315I-associated resistance to nilotinib, but the supplied abstract does not explicitly state the candidate chronic myeloid leukemia disease context. The candidate has no explicit gene field.",
        "MEDIUM",
    ),
}


def parse_source_units(markdown: str) -> dict[str, str]:
    pattern = re.compile(
        r"^## (?P<id>SU-[^\n]+)\n.*?^TEXT:\n\n(?P<text>.*?)(?=^## SU-|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    return {match["id"]: match["text"].strip() for match in pattern.finditer(markdown)}


def abbreviated_assertion(candidate: dict[str, object]) -> str:
    subject = candidate["subject"]["label"]
    predicate = candidate["predicate"]
    obj = candidate["object"]["label"]
    return f"{subject} / {predicate} / {obj}"


def main() -> None:
    DRAFT_ROOT.mkdir(exist_ok=True)
    records: list[dict[str, object]] = []
    for sample_id in sorted(DRAFTS):
        pack_dir = PACK_ROOT / sample_id
        candidate = json.loads((pack_dir / "candidate.json").read_text(encoding="utf-8"))
        overview = (pack_dir / "source_overview.md").read_text(encoding="utf-8")
        source_units = parse_source_units((pack_dir / "source_units.md").read_text(encoding="utf-8"))
        assert candidate["sample_id"] == sample_id
        assert candidate["candidate_id"] in overview

        source = DRAFTS[sample_id]
        for unit_id in source["unit_ids"]:
            assert unit_id in source_units, f"{sample_id}: unknown SourceUnit {unit_id}"
        assert any(source["quote"] in source_units[unit_id] for unit_id in source["unit_ids"]), (
            f"{sample_id}: draft quote is not literal in a declared SourceUnit"
        )

        disease, gene, alteration, drug, direction, evidence_type = source["fields"]
        record = {
            "sample_id": sample_id,
            "candidate_id": candidate["candidate_id"],
            "annotation_status": "AI_DRAFT",
            "disease_supported": disease,
            "gene_supported": gene,
            "alteration_supported": alteration,
            "drug_supported": drug,
            "direction_supported": direction,
            "evidence_type_supported": evidence_type,
            "overall_gold_draft": source["overall"],
            "gold_source_unit_ids_draft": source["unit_ids"],
            "gold_quote_draft": source["quote"],
            "reasoning_summary": source["reasoning"],
            "uncertainty": source["uncertainty"],
            "author_review_required": True,
        }
        (DRAFT_ROOT / f"{sample_id}_ai_draft.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        records.append(
            {
                "sample_id": sample_id,
                "candidate_id": candidate["candidate_id"],
                "assertion": abbreviated_assertion(candidate),
                "overall_draft": source["overall"],
                "uncertainty": source["uncertainty"],
                "reasoning_summary": source["reasoning"],
            }
        )

    overall_counts = Counter(record["overall_draft"] for record in records)
    uncertainty_counts = Counter(record["uncertainty"] for record in records)
    summary = {
        "annotation_status": "AI_DRAFT",
        "system_output_used": False,
        "author_review_required": True,
        "papers_annotated": len(records),
        "overall_draft_counts": dict(sorted(overall_counts.items())),
        "uncertainty_counts": dict(sorted(uncertainty_counts.items())),
        "high_uncertainty_cases": [
            {"sample_id": record["sample_id"], "reasoning_summary": record["reasoning_summary"]}
            for record in records
            if record["uncertainty"] == "HIGH"
        ],
        "records": records,
    }
    (DRAFT_ROOT / "ai_annotation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# AI-assisted paper pre-annotation summary",
        "",
        "These are AI_DRAFT annotations made only from the frozen candidate and source pack. They are not final gold and require author review.",
        "",
        "| sample_id | candidate_id | disease | gene | alteration | drug | direction | evidence_type | overall_draft | uncertainty |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for sample_id in sorted(DRAFTS):
        record = json.loads((DRAFT_ROOT / f"{sample_id}_ai_draft.json").read_text(encoding="utf-8"))
        lines.append(
            "| {sample_id} | {candidate_id} | {disease_supported} | {gene_supported} | {alteration_supported} | {drug_supported} | {direction_supported} | {evidence_type_supported} | {overall_gold_draft} | {uncertainty} |".format(**record)
        )
    lines += ["", "## High-uncertainty cases", ""]
    for record in summary["high_uncertainty_cases"]:
        lines.append(f"- **{record['sample_id']}** — {record['reasoning_summary']}")
    lines += ["", "## Draft distribution", ""]
    for label in ("FULL_SUPPORT", "PARTIAL_SUPPORT", "NO_SUPPORT", "CONTRADICTORY", "UNVERIFIABLE"):
        lines.append(f"- {label}: {overall_counts[label]}")
    (DRAFT_ROOT / "ai_annotation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
