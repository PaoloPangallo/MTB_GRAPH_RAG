"""Scrive ``graph_candidate_repository/3.0`` e il mapping v2→v3.

Uso::

    python -m gca_v3.build_repository

``graph_candidate_repository/2.0`` non viene letto per costruire v3 e non viene
mai scritto: lo script si rifiuta di procedere se il suo hash è cambiato.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.rq1.kg_source import EligiblePathBuilder, FrozenKnowledgeGraph

from . import CONTRACT_VERSION, REPOSITORY_VERSION
from .contract import SCHEMA, schema_hash
from .materialize import MATERIALIZER_VERSION, MaterializerV3

REPO_ROOT = Path(__file__).resolve().parents[1]
KG_ROOT = REPO_ROOT.parent / "data_expl" / "DatasetTESI" / "Dataset TESI" / "Clean_Graph_Data"
BASE = REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims" / "graph_candidate_repository"
V2 = BASE / "2.0"
V3 = BASE / "3.0"
EVAL_OUT = REPO_ROOT / "evaluation" / "gca_v3"

#: Hash atteso di v2. Se cambia, v2 è stato toccato: lo script si ferma.
V2_EXPECTED_SHA256 = "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d"


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "UNKNOWN"


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def main() -> int:
    actual = _sha_file(V2 / "candidates.jsonl")
    if actual != V2_EXPECTED_SHA256:
        raise SystemExit(
            "[gca-v3] RIFIUTO: graph_candidate_repository/2.0 risulta modificato.\n"
            f"  atteso : {V2_EXPECTED_SHA256}\n  attuale: {actual}"
        )
    print(f"[gca-v3] v2 invariato ({actual[:16]}…)")

    graph = FrozenKnowledgeGraph(KG_ROOT)
    fingerprint = graph.fingerprint()
    materializer = MaterializerV3(graph)
    candidates = materializer.build()
    print(f"[gca-v3] candidate v3: {len(candidates)}")

    V3.mkdir(parents=True, exist_ok=True)
    EVAL_OUT.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ candidates
    with (V3 / "candidates.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    repository_hash = _sha_file(V3 / "candidates.jsonl")

    # ----------------------------------------------------------- indici v3
    # Indice compatto: serve a filtrare senza rileggere candidates.jsonl, quindi
    # è serializzato senza indentazione. Nessuna informazione è persa.
    (V3 / "candidate_index.json").write_text(
        json.dumps({
            c.candidate_id: [
                c.materialization_rule_id, c.source_alignment_status,
                c.intervention_structure, c.alteration_parse_status,
            ]
            for c in candidates
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _write_json(V3 / "candidate_index_schema.json", {
        "format": "candidate_id -> [materialization_rule_id, source_alignment_status, "
                  "intervention_structure, alteration_parse_status]",
    })
    with (V3 / "lineage_index.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for c in candidates:
            handle.write(json.dumps({
                "candidate_id": c.candidate_id,
                "source_path_ids": c.source_path_ids,
                "node_ids": c.node_ids,
                "edge_ids": c.edge_ids,
                "evidence_record_ids": c.evidence_record_ids,
            }, ensure_ascii=False, sort_keys=True) + "\n")

    # ------------------------------------------------------- mapping v2→v3
    mapping_rows = _build_mapping(graph, candidates)
    with (V3 / "v2_mapping.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in mapping_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (EVAL_OUT / "v2_to_v3_mapping.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "v2_candidate_id", "v3_candidate_id", "relation_type", "reason_code", "notes"])
        writer.writeheader()
        writer.writerows(mapping_rows)

    # --------------------------------------------------------------- schema
    _write_json(V3 / "schema.json", SCHEMA)

    # ------------------------------------------------------------- manifest
    alignment = Counter(c.source_alignment_status for c in candidates)
    structure = Counter(c.intervention_structure for c in candidates)
    parse = Counter(c.alteration_parse_status for c in candidates)
    compound = sum(1 for c in candidates if c.alteration_parse_status in {"PARSED_EXACT", "PARSED_WITH_WARNINGS"})
    with_pmid = sum(1 for c in candidates if any(i.get("pmid") for i in c.document_identifiers))
    with_nct = sum(1 for c in candidates if any(i.get("nct") for i in c.document_identifiers))
    without_doc = sum(1 for c in candidates if not c.document_identifiers)

    manifest = {
        "repository_version": REPOSITORY_VERSION,
        "contract_version": CONTRACT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "EXPERIMENTAL_NOT_RUNTIME_DEFAULT",
        "source_export": str(KG_ROOT),
        "source_export_hash": fingerprint["corpus_fingerprint"],
        "materializer_commit": _git("rev-parse", "HEAD"),
        "materializer_version": MATERIALIZER_VERSION,
        "predecessor": {
            "repository": "graph_candidate_repository/2.0",
            "candidates_sha256": V2_EXPECTED_SHA256,
            "unchanged": True,
        },
        "eligible_path_count": sum(len(c.source_path_ids) for c in candidates),
        "candidate_count": len(candidates),
        "source_aligned_count": alignment.get("SOURCE_ALIGNED", 0),
        "does_not_support_count": alignment.get("SOURCE_DOES_NOT_SUPPORT", 0),
        "contradicted_count": alignment.get("SOURCE_CONTRADICTS", 0),
        "neutral_count": alignment.get("SOURCE_NEUTRAL", 0),
        "alignment_unclear_count": alignment.get("SOURCE_ALIGNMENT_UNCLEAR", 0),
        "alignment_not_available_count": alignment.get("SOURCE_ALIGNMENT_NOT_AVAILABLE", 0),
        "compound_alteration_count": compound,
        "unsupported_alteration_expression_count": (
            parse.get("MALFORMED_EXPRESSION", 0) + parse.get("UNSUPPORTED_EXPRESSION", 0)
            + parse.get("AMBIGUOUS_OPERATOR", 0)),
        "alteration_parse_status_distribution": dict(parse),
        "single_agent_count": structure.get("SINGLE_AGENT", 0),
        "confirmed_combination_count": structure.get("COMBINATION_CONFIRMED", 0),
        "unresolved_multi_component_count": structure.get("MULTI_COMPONENT_UNRESOLVED", 0),
        "intervention_structure_distribution": dict(structure),
        "candidates_with_pmid": with_pmid,
        "candidates_with_nct": with_nct,
        "candidates_without_document_identifiers": without_doc,
        "repository_hash": repository_hash,
        "schema_hash": schema_hash(),
        "excluded_paths": len(materializer.excluded),
        "exclusion_reasons": dict(Counter(e["reason"] for e in materializer.excluded)),
        "known_limitations": [
            "REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT: l'export non distingue "
            "combinazione, alternativa e sequenza; i record multi-farmaco sono "
            "MULTI_COMPONENT_UNRESOLVED e non eleggibili al match esatto "
            "sull'intervento.",
            "component_role vale sempre UNKNOWN: l'export non contiene ruoli.",
            "CONTRADICTS_ASSERTION e NEUTRAL_OR_NO_DIFFERENCE non sono prodotti: "
            "evidence_direction ha solo Supports / Does Not Support / vuoto.",
            "Le regole non-Evidence (gene-drug, trial, companion diagnostic) non "
            "portano polarita' ne' alterazioni: restano NOT_REPORTED / MISSING.",
            "Nessuna normalizzazione farmacologica: BGJ398 e infigratinib restano "
            "termini distinti (KNOWN_DRUG_SYNONYM_GAP).",
        ],
    }
    _write_json(V3 / "manifest.json", manifest)

    readme = f"""# graph_candidate_repository/3.0

Contratto `{CONTRACT_VERSION}`. **Non è il default del runtime**: la versione si
sceglie con `GRAPH_CANDIDATE_REPOSITORY_VERSION=2.0|3.0`, e il default resta
`2.0`.

Il cambio rispetto a 2.0 è **major**: cambia il significato degli oggetti, non
solo la loro serializzazione.

| | 2.0 | 3.0 |
|---|---|---|
| Candidate | 46 864 | {len(candidates)} |
| Polarità della fonte | solo in `source_properties` | campo di primo livello |
| Alterazioni composte | prima variante | espressione completa + AST |
| Record multi-farmaco | una candidate per farmaco | una candidate per regime |

Una GraphCandidateAssertion significa **relazione candidata derivata dal
Knowledge Graph** — non claim degli autori, non evidenza documentale, non verità
clinica, non raccomandazione, non supporto verificato.

Vedi `docs/graph_candidate_v3/`.
"""
    (V3 / "README.md").write_text(readme, encoding="utf-8")

    print(f"[gca-v3] repository_hash = {repository_hash}")
    print(f"[gca-v3] alignment  = {dict(alignment)}")
    print(f"[gca-v3] structure  = {dict(structure)}")
    print(f"[gca-v3] parse      = {dict(parse)}")
    print(f"[gca-v3] mapping    = {dict(Counter(r['relation_type'] for r in mapping_rows))}")

    final = _sha_file(V2 / "candidates.jsonl")
    if final != V2_EXPECTED_SHA256:
        raise SystemExit("[gca-v3] ERRORE: v2 modificato durante l'esecuzione")
    print("[gca-v3] v2 ancora invariato dopo la scrittura")
    return 0


def _build_mapping(graph: FrozenKnowledgeGraph, candidates) -> list[dict]:
    """Relazione v2 ↔ v3, calcolata via identità di path condivisa.

    Il mapping è ricavato dai **path sorgente**, non convertendo i record v2:
    ogni candidate v2 e ogni candidate v3 dichiara i path da cui deriva, e i due
    insiemi si accoppiano su quelli.
    """
    v2_paths = EligiblePathBuilder(graph).build()
    v2_by_path = {}
    for path in v2_paths:
        v2_by_path[path.path_id] = path

    # path v2 -> candidate_id v2 (ricostruito con la stessa identità di v2)
    from evaluation.rq1.compare import MaterializationComparator, load_candidates
    v2_records = list(load_candidates(V2 / "candidates.jsonl"))
    comparator = MaterializationComparator(v2_paths, v2_records)
    result = comparator.compare()
    v2_id_by_path = {c.path_id: c.candidate_id for c in result["comparisons"] if c.matched}

    # path v3 (in id v2) -> candidate v3
    v3_by_v2_path = defaultdict(list)
    for candidate in candidates:
        for path_id in candidate.source_path_ids:
            v3_by_v2_path[_to_v2_path_id(path_id)].append(candidate.candidate_id)

    rows: list[dict] = []
    seen_v3: set[str] = set()
    for path_id, v2_id in sorted(v2_id_by_path.items()):
        v3_ids = v3_by_v2_path.get(path_id, [])
        if not v3_ids:
            rows.append({"v2_candidate_id": v2_id, "v3_candidate_id": "",
                         "relation_type": "UNMAPPED", "reason_code": "NO_V3_PATH",
                         "notes": path_id})
            continue
        for v3_id in v3_ids:
            siblings = sum(1 for p, ids in v3_by_v2_path.items() if v3_id in ids)
            if siblings > 1:
                relation, reason = "MANY_TO_ONE", "REGIMEN_UNIT_MERGED"
                notes = "più path v2 (uno per farmaco) confluiscono in una candidate di regime"
            else:
                relation, reason, notes = "ONE_TO_ONE", "PATH_PRESERVED", ""
            rows.append({"v2_candidate_id": v2_id, "v3_candidate_id": v3_id,
                         "relation_type": relation, "reason_code": reason, "notes": notes})
            seen_v3.add(v3_id)

    for candidate in candidates:
        if candidate.candidate_id not in seen_v3:
            rows.append({"v2_candidate_id": "", "v3_candidate_id": candidate.candidate_id,
                         "relation_type": "NEWLY_RECOVERED_COMPOUND",
                         "reason_code": "NO_V2_COUNTERPART", "notes": ""})
    return rows


def _to_v2_path_id(path_id: str) -> str:
    """Traduce un path id v3 nella forma v2, per l'accoppiamento."""
    return path_id.replace("gca/3.0/evidence-to-intervention#", "gca/2.0/evidence-to-drug#") \
                  .replace("gca/3.0/", "gca/2.0/")


if __name__ == "__main__":
    sys.exit(main())
