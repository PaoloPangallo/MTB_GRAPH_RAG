"""Probe D — §12 Quote validation.

Esegue il validatore REALMENTE collegato al percorso LIVE
(``live_providers.validate_fn`` -> ``validator_v2.validate_enrichment_v2``) e,
per confronto, il validatore v1 (``validator.validate_enrichment``), sugli otto
scenari del §12 piu' varianti.

Le SourceUnit sono sintetiche e costruite dalla sonda: non serve la cache
documentale, e ogni caso ha un atteso noto per costruzione.

Invarianti da falsificare:
    invented_quote_accepted             = 0
    invented_sourceunit_accepted        = 0
    quote_from_wrong_document_accepted  = 0

Output: JSONL su stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))

from backend.research_pipeline import live_providers as lp  # noqa: E402
from backend.research_pipeline.enrichment import validator as v1  # noqa: E402

# --------------------------------------------------------------- fixture

DOC_A_TEXT = (
    "In this phase III trial, patients with metastatic colorectal cancer harbouring "
    "KRAS G12D mutations did not derive benefit from panitumumab monotherapy compared "
    "with best supportive care."
)
DOC_B_TEXT = (
    "Encorafenib in combination with cetuximab produced an objective response rate of "
    "20% in BRAF V600E metastatic colorectal cancer."
)

UNITS = {
    "SU-A1": {"source_unit_id": "SU-A1", "document_id": "DOC-A", "text": DOC_A_TEXT},
    "SU-B1": {"source_unit_id": "SU-B1", "document_id": "DOC-B", "text": DOC_B_TEXT},
}

PAPER_A = {"bundle_id": "EB-A", "document_id": "DOC-A",
           "source_unit_ids": ["SU-A1"], "resolved_source_unit_ids": ["SU-A1"]}

CANDIDATE = {
    "candidate_id": "GCA-TEST", "direction": "Does Not Support",
    "disease": [{"label": "Colorectal Cancer"}],
    "biomarkers": [{"label": "KRAS G12D"}],
    "interventions": [{"label": "panitumumab"}],
    "source_properties": {"evidence": {"evidence_statement": "irrelevant"}},
}

DRUG = "panitumumab"

LITERAL = "did not derive benefit from panitumumab monotherapy"
ALTERED = "did derive benefit from panitumumab monotherapy"      # una parola cambiata
FROM_B = "Encorafenib in combination with cetuximab"             # altro documento


def v2_args(decision="QUOTE", source_unit_id="SU-A1", quote="", summary="", abstention=""):
    return {"decision": decision, "source_unit_id": source_unit_id,
            "author_claim_quote": quote, "author_context_summary": summary,
            "abstention_reason": abstention}


CASES = [
    ("D-A_quote_letterale_valida", "A. quote letterale valida",
     v2_args(quote=LITERAL, summary="Patients did not derive benefit from panitumumab monotherapy."),
     "ACCEPT"),

    ("D-B_quote_inesistente", "B. quote inesistente nel documento",
     v2_args(quote="Panitumumab significantly prolonged overall survival in this cohort.",
             summary="Panitumumab prolonged survival."),
     "REJECT"),

    ("D-C_quote_quasi_identica", "C. quote quasi identica ma modificata (polarita' invertita)",
     v2_args(quote=ALTERED, summary="Patients did derive benefit from panitumumab."),
     "REJECT"),

    ("D-D_quote_da_altra_sourceunit", "D. quote proveniente da un'altra SourceUnit dello stesso set",
     v2_args(source_unit_id="SU-A1", quote=FROM_B, summary="Encorafenib with cetuximab produced responses."),
     "REJECT"),

    ("D-E_quote_da_altro_documento", "E. SourceUnit di un altro documento, non nel paper bundle",
     v2_args(source_unit_id="SU-B1", quote=FROM_B, summary="Encorafenib with cetuximab produced responses."),
     "REJECT"),

    ("D-F_sourceunit_inventata", "F. SourceUnit inventata",
     v2_args(source_unit_id="SU-DOES-NOT-EXIST", quote=LITERAL, summary="Patients did not derive benefit."),
     "REJECT"),

    ("D-G_quote_vuota", "G. quote vuota",
     v2_args(quote="", summary="Some summary."),
     "REJECT"),

    ("D-H_abstain_pulito", "H. ABSTAIN corretto",
     v2_args(decision="ABSTAIN", source_unit_id="", quote="", summary="", abstention="NO_RELEVANT_PASSAGE"),
     "ABSTAIN"),

    ("D-I_abstain_con_campi", "H-bis. ABSTAIN con campi popolati (incoerente)",
     v2_args(decision="ABSTAIN", source_unit_id="SU-A1", quote=LITERAL, summary="x",
             abstention="NO_RELEVANT_PASSAGE"),
     "ABSTAIN_INCONSISTENT"),

    ("D-J_quote_con_ellissi", "quote non contigua (ellissi)",
     v2_args(quote="patients with metastatic colorectal cancer ... panitumumab monotherapy",
             summary="Patients with colorectal cancer and panitumumab."),
     "REJECT"),

    ("D-K_raccomandazione_clinica", "summary contenente raccomandazione clinica",
     v2_args(quote=LITERAL,
             summary="These patients should receive panitumumab as first line therapy."),
     "REJECT"),

    ("D-L_summary_ungrounded", "summary non ancorato alla quote",
     v2_args(quote=LITERAL,
             summary="Immunotherapy combinations demonstrate durable remissions across many tumours."),
     "REJECT"),

    ("D-M_status_language", "summary che pretende di assegnare uno status canonico",
     v2_args(quote=LITERAL,
             summary="The evidence for panitumumab is DIRECT and belongs in the primary bucket."),
     "REJECT"),

    ("D-N_farmaco_diverso", "farmaco non presente nel passaggio",
     v2_args(quote="metastatic colorectal cancer harbouring",
             summary="Metastatic colorectal cancer harbouring mutations."),
     "REJECT"),
]

ACCEPTED_V2 = ("ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")
ACCEPTED_V1 = ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING")


def main():
    from backend.research_pipeline.orchestrator import _accepted_for_gates

    for case_id, label, args, expected in CASES:
        r2 = lp.validate_fn("V2_TRANSPORT_VALID", dict(args), candidate=CANDIDATE,
                            paper_bundle=PAPER_A, source_units_by_id=UNITS,
                            requested_drug=DRUG)
        outcome2 = r2["outcome"]
        accepted2 = outcome2 in ACCEPTED_V2

        # v1 sullo stesso scenario, per confronto (contratto diverso)
        enr_v1 = {"candidate_id": CANDIDATE["candidate_id"], "paper_id": PAPER_A["bundle_id"],
                  "source_unit_id": args["source_unit_id"], "drug": DRUG,
                  "author_claim_quote": args["author_claim_quote"],
                  "author_context_summary": args["author_context_summary"],
                  "evidence_kind": "RESISTANCE",
                  "abstain": args["decision"] == "ABSTAIN"}
        r1 = v1.validate_enrichment("FORCED_TOOL_VALID", enr_v1, candidate=CANDIDATE,
                                    paper_bundle=PAPER_A, source_units_by_id=UNITS,
                                    requested_drug=DRUG)
        accepted1 = r1["outcome"] in ACCEPTED_V1

        # cio' che l'orchestratore fa realmente dell'esito: None = non raggiunge i gate
        gate_admission = _accepted_for_gates(outcome2)

        ok = {
            "ACCEPT": accepted2,
            "REJECT": not accepted2,
            "ABSTAIN": outcome2 == "ENRICHMENT_V2_ABSTAINED",
            "ABSTAIN_INCONSISTENT": outcome2 == "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS",
        }[expected]

        print(json.dumps({
            "probe": "D", "case_id": case_id, "scenario": label,
            "expected": expected,
            "validator_v2_outcome": outcome2,
            "validator_v2_reason_codes": r2.get("reason_codes"),
            "validator_v2_accepted": accepted2,
            "validator_v1_outcome": r1["outcome"],
            "validator_v1_accepted": accepted1,
            "reaches_deterministic_gates": gate_admission is not None,
            "gate_admission_value": gate_admission,
            "behaves_as_expected": ok,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
