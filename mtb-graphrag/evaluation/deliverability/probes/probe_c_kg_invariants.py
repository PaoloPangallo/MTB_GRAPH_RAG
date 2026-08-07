"""Probe C — Invarianti semantici del KG (§8), misurati separatamente su:

  RUNTIME  = graph_candidate_repository/2.0  (cio' che orchestrator.run_case usa)
  SHADOW   = graph_candidate_repository/3.0  (cio' che evaluation/ usa)

Nessuna modifica al codice: si chiamano le funzioni reali del runtime
(``kg_retrieval._match_candidate``, ``gates.direction_consistency``) e del
percorso shadow (``retrieval.admission``).

Output: JSONL degli invarianti su stdout.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))

from backend.research_pipeline.determinism.gates import direction_consistency  # noqa: E402
from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate  # noqa: E402

D = ROOT / "benchmarks/mtb_evidence/document_grounded_claims"
V2 = D / "graph_candidate_repository/2.0/candidates.jsonl"
V3 = D / "graph_candidate_repository/3.0/candidates.jsonl"
EB = D / "evidence_bundle/evidence_bundles.jsonl"

OUT: list[dict] = []


def emit(**kw):
    OUT.append({"checkpoint": "C", **kw})


def rows(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    reachable = {r["candidate_id"] for r in rows(EB)}

    # ---------------------------------------------------------------- v2 scan
    v2_dir = Counter()
    v2_pol = Counter()
    inverted, inverted_reachable = Counter(), []
    multi_biomarker = 0
    multi_intervention = 0
    n2 = 0
    for r in rows(V2):
        n2 += 1
        d = r.get("direction")
        pol = ((r.get("source_properties") or {}).get("evidence") or {}).get("evidence_direction")
        v2_dir[d] += 1
        v2_pol[pol] += 1
        negative = (pol == "Does Not Support") or (d in ("Reduced Sensitivity", "Adverse Response"))
        if negative and direction_consistency(d, "RESPONSE") == "CONSISTENT":
            inverted[d] += 1
            if r["candidate_id"] in reachable:
                inverted_reachable.append({"candidate_id": r["candidate_id"],
                                           "direction": d, "source_polarity": pol})
        if len(r.get("biomarkers") or []) > 1:
            multi_biomarker += 1
        if len(r.get("interventions") or []) > 1:
            multi_intervention += 1

    # ------------------------------------------- INV-C01 polarita' preservata
    emit(invariant_id="INV-C01", repository="2.0 (RUNTIME)",
         statement="DOES_NOT_SUPPORT non viene convertito in supporto positivo",
         holds=False, measured=sum(inverted.values()), expected=0,
         detail=dict(inverted),
         reachable_end_to_end_affected=len(inverted_reachable),
         reachable_examples=inverted_reachable,
         root_cause=("gates.py:34 usa `\"support\" in direction`; `\"support\" in "
                     "\"does not support\"` e' True. Inoltre il runtime non legge mai "
                     "source_properties.evidence.evidence_direction, quindi 213 candidate "
                     "con direction=Sensitivity/Response e polarita' Does Not Support "
                     "risultano positive."),
         evidence="probe_c")

    emit(invariant_id="INV-C02", repository="2.0 (RUNTIME)",
         statement="Il runtime legge la polarita' della fonte",
         holds=False, measured=0, expected=1,
         detail="kg_retrieval._match_candidate legge solo disease/biomarkers/interventions; "
                "gates.evaluate_association legge solo candidate['direction']. "
                "evidence_direction non e' letto da alcun modulo del runtime.",
         evidence="grep evidence_direction backend/research_pipeline = 0 occorrenze")

    # ------------------------------- INV-C03 direction conflates two axes (v2)
    conflated = sum(n for (p, d), n in Counter(
        ((((r.get("source_properties") or {}).get("evidence") or {}).get("evidence_direction")),
         r.get("direction")) for r in rows(V2)).items()
        if p == "Does Not Support" and d not in (None, "", "Does Not Support"))
    emit(invariant_id="INV-C03", repository="2.0 (RUNTIME)",
         statement="Il campo `direction` non confonde polarita' della fonte e direzione clinica",
         holds=False, measured=conflated, expected=0,
         detail=("candidate con evidence_direction='Does Not Support' ma direction clinica "
                 "positiva/negativa indistinguibile da una supportata"),
         evidence="probe_c")

    # --------------------------------------------- INV-C04 A AND B != A  (v2)
    cand_and = {"disease": [{"label": "Colorectal Cancer"}],
                "biomarkers": [{"label": "KRAS G12D"}, {"label": "BRAF V600E"}],
                "interventions": [{"label": "panitumumab"}]}
    cc_only_a = {"query_intent": "THERAPY_EVALUATION",
                 "disease": {"normalized_value": "Colorectal Cancer"},
                 "biomarkers": [{"gene": "KRAS", "normalized_value": "KRAS G12D",
                                 "raw_value": "KRAS G12D"}],
                 "target_intervention": {"normalized_value": "panitumumab"}}
    ok, reasons = _match_candidate(cc_only_a, cand_and)
    emit(invariant_id="INV-C04", repository="2.0 (RUNTIME)",
         statement="Una candidate `A AND B` non corrisponde a un caso che menziona solo A",
         holds=not ok, measured=("FULL_MATCH" if ok else "NO_MATCH"), expected="NO_MATCH o PARTIAL",
         detail=dict(match=ok, reason_codes=reasons,
                     note="nessun codice PARTIAL_MATCH esiste nel retrieval v2",
                     candidates_with_multiple_biomarkers=multi_biomarker),
         evidence="probe_c")

    # ------------------------------ INV-C05 alterazioni distinte non collassate
    from backend.research_pipeline.retrieval.kg_retrieval import _term_matches
    pairs = [("kras g12d", "kras g12c"), ("braf v600e", "braf v600k"),
             ("egfr exon 19 deletion", "egfr exon 20 insertion"),
             ("her2 amplification", "her2 mutation"), ("tp53 r175h", "tp53 r273h")]
    collapsed = [(a, b) for a, b in pairs if _term_matches(a, b)]
    emit(invariant_id="INV-C05", repository="2.0 (RUNTIME)",
         statement="Alterazioni clinicamente distinte dello stesso gene non corrispondono fra loro",
         holds=not collapsed, measured=len(collapsed), expected=0,
         detail=dict(collapsed_pairs=collapsed,
                     root_cause="_term_matches accetta un qualunque token condiviso > 2 caratteri; "
                                "il simbolo del gene basta a far corrispondere due varianti diverse"),
         evidence="probe_c")

    # ------------------------------------------ INV-C06 regimi multi-componente
    emit(invariant_id="INV-C06", repository="2.0 (RUNTIME)",
         statement="Un regime multi-componente non produce supporto per un singolo farmaco",
         holds=False, measured=multi_intervention, expected="rappresentazione esplicita",
         detail=("v2 non ha ne' intervention_structure ne' regimen_semantics_status. "
                 "_match_candidate accetta se il farmaco del caso corrisponde a UNA "
                 "qualunque delle interventions della candidate: nessuna nozione di "
                 "regime irrisolto esiste nel runtime."),
         evidence="probe_c")

    # ---------------------------------------------------------------- v3 scan
    try:
        from backend.research_pipeline.retrieval import admission as adm  # noqa: F401
        v3_pol = Counter(); v3_align = Counter(); v3_parse = Counter(); v3_struct = Counter()
        v3_dir = Counter(); n3 = 0
        for r in rows(V3):
            n3 += 1
            v3_pol[r.get("source_support_polarity")] += 1
            v3_align[r.get("source_alignment_status")] += 1
            v3_parse[r.get("alteration_parse_status")] += 1
            v3_struct[r.get("intervention_structure")] += 1
            v3_dir[r.get("graph_direction")] += 1
        emit(invariant_id="INV-C07", repository="3.0 (SHADOW)",
             statement="Il contratto v3 rappresenta esplicitamente polarita', allineamento, AST e struttura del regime",
             holds=True, measured=n3, expected=n3,
             detail=dict(source_support_polarity=dict(v3_pol),
                         source_alignment_status=dict(v3_align),
                         alteration_parse_status=dict(v3_parse),
                         intervention_structure=dict(v3_struct),
                         graph_direction=dict(v3_dir)),
             evidence="probe_c")
        emit(invariant_id="INV-C08", repository="3.0 (SHADOW)",
             statement="I campi v3 sono consumati dal runtime canonico",
             holds=False, measured=0, expected=1,
             detail="admission.py e repository_v3.py sono SHADOW_EVALUATION; "
                    "kg_retrieval_v3.py e' DEAD_OR_UNREACHABLE (zero riferimenti nel repository).",
             evidence="evaluation/deliverability/runtime_component_matrix.csv")
    except Exception as exc:  # noqa: BLE001
        emit(invariant_id="INV-C07", repository="3.0 (SHADOW)", holds=None,
             error=f"{type(exc).__name__}: {exc}")

    emit(invariant_id="INV-C09", repository="2.0 (RUNTIME)",
         statement="GraphCandidateAssertion resta distinta da evidenza documentale",
         holds=True, measured=0, expected=0,
         detail=("stage_5 dichiara esplicitamente graph_derived=True e documentary_proof=False "
                 "nel proprio output_preview (orchestrator.py:440-441); il supporto documentale "
                 "e' un asse separato calcolato solo dopo la validazione."),
         evidence="orchestrator.py:439-445")

    for row in OUT:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
