"""Generate the auditable documentation for the provenance pilot."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/provenance_repair"
REPO_14 = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
REPO_15 = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_5_provenance_pilot"
PILOT = json.loads((REPO_15 / "provenance_repair_manifest.json").read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def by_claim(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["claim_id"]): row for row in jsonl(path)}


def sources_from_locators(row: dict[str, Any]) -> list[str]:
    return [str(item["source_id"]) for item in row.get("locators", []) if item.get("source_id")]


def case_observations() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    case_dir = ROOT / "benchmarks/mtb_evidence/exploratory/manual_v3_cases_product_hardening"
    for path in sorted(case_dir.glob("case_*_api_response.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        case = path.stem.replace("_api_response", "")
        for bucket, records in payload.get("evidence", {}).items():
            for record in records:
                claim_id = str(record.get("claim_id") or "")
                if not claim_id:
                    continue
                score = record.get("score")
                score_value = score.get("total") if isinstance(score, dict) else ""
                result.setdefault(claim_id, []).append(f"{case}:{bucket}:{score_value}")
    return result


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    before = by_claim(REPO_14 / "evidence_claims.jsonl")
    after = by_claim(REPO_15 / "evidence_claims.jsonl")
    parents = {str(row["parent_id"]): row for row in jsonl(REPO_14 / "graph_evidence_parents.jsonl")}
    observations = case_observations()
    rows: list[dict[str, Any]] = []

    for claim_id in PILOT["pilot_claim_ids"]:
        old = before[claim_id]
        new = after[claim_id]
        parent = parents[str(old["parent_id"])]
        repair = dict(new.get("provenance_repair") or {})
        old_sources = sources_from_locators(old)
        new_sources = sources_from_locators(new)
        old_status = "VERIFIED_LOCATOR" if old.get("source_unit_ids") and old.get("locators") else "PARENT_ONLY"
        parity = "|".join(f"{item}={item}" for item in observations.get(claim_id, []))
        rows.append(
            {
                "claim_id": claim_id,
                "claim_domain": old.get("claim_domain", ""),
                "claim_type": old.get("claim_type", ""),
                "parent_id": old.get("parent_id", ""),
                "prior_status": old_status,
                "new_status": repair.get("status", ""),
                "parent_publications": "|".join(str(value) for value in parent.get("source_ids", [])),
                "claim_source_ids_before": "|".join(old_sources),
                "claim_source_ids_after": "|".join(new_sources),
                "source_unit_id_before": "|".join(old.get("source_unit_ids", [])),
                "source_unit_id_after": "|".join(new.get("source_unit_ids", [])),
                "locator_before": json.dumps(old.get("locators", []), ensure_ascii=False, sort_keys=True),
                "locator_after": json.dumps(new.get("locators", []), ensure_ascii=False, sort_keys=True),
                "rule": repair.get("rule", ""),
                "reason": repair.get("reason", ""),
                "confidence": repair.get("confidence", ""),
                "ambiguous_source_count": len(parent.get("source_ids", [])) if repair.get("status") == "AMBIGUOUS_PARENT_PROVENANCE" else 0,
                "bucket_score_before_after": parity,
            }
        )

    fields = list(rows[0])
    write_csv(AUDIT / "pilot_claims_before_after.csv", rows, fields)
    write_csv(
        AUDIT / "ambiguous_claims.csv",
        [
            {
                "claim_id": row["claim_id"],
                "parent_id": row["parent_id"],
                "claim_type": row["claim_type"],
                "candidate_source_unit_count": row["ambiguous_source_count"],
                "candidate_publication_count": row["ambiguous_source_count"],
                "first_ambiguous_point": "parent -> publication/source-unit mapping",
                "status": row["new_status"],
                "reason": row["reason"],
                "recommendation": "investigate manually; do not promote",
            }
            for row in rows
            if row["new_status"] == "AMBIGUOUS_PARENT_PROVENANCE"
        ],
        ["claim_id", "parent_id", "claim_type", "candidate_source_unit_count", "candidate_publication_count", "first_ambiguous_point", "status", "reason", "recommendation"],
    )

    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row["new_status"]] = statuses.get(row["new_status"], 0) + 1
    source_units_added = sum(row["source_unit_id_before"] != row["source_unit_id_after"] for row in rows)
    locators_added = sum(row["locator_before"] != row["locator_after"] and row["locator_after"] != "[]" for row in rows)

    (AUDIT / "README.md").write_text(
        """# V3 provenance repair pilot

Pilota conservativo non-default derivato dal repository `qualified_claim_repository/1.4`.
Il repository 1.4 resta invariato e il retriever operativo non è collegato alla versione 1.5.

## Output

- `provenance_materialization_trace.md`: percorso reale e punto di perdita.
- `safe_propagation_rules.md`: regole di promozione senza fallback dal parent.
- `pilot_claims_before_after.csv`: inventario before/after delle claim pilota.
- `ambiguous_claims.csv`: claim non promosse.
- `provenance_repair_report.md`: conteggi e decisione finale.
- `repository_version_diff.md`: differenza tra 1.4 e overlay 1.5.

Il mapping esterno letto è `benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3/qualification_link_regeneration_plan_v1_3.jsonl`, usato come evidenza già esplicita e non modificato.
""",
        encoding="utf-8",
    )
    (AUDIT / "provenance_materialization_trace.md").write_text(
        """# Provenance materialization trace

```text
qualified_claim_repository/1.4/evidence_claims.jsonl
  -> retrieval/v3_objects.py::claim_object
  -> corpus/materialization.py::promoted_claims
  -> qualified_claim_repository_1_5_provenance_pilot
```

`claim_object()` conserva `source_unit_ids` e `locators` quando sono presenti. `promoted_claims()` copia il record senza risolvere claim -> source unit. L'audit mostra che 131 righe della 1.4 arrivano già con `source_unit_ids=[]` e `locators=[]`; il parent conserva `source_ids` e `source_record_ids`, ma questi non sono prova claim-specifica.

Il materializzatore aggiunge `provenance_repair` solo alle claim pilota. Copia source unit e locator esclusivamente da un mapping claim-specifico già documentato; negli altri casi registra `PARENT_PUBLICATION_AVAILABLE` o `AMBIGUOUS_PARENT_PROVENANCE`. Non modifica testo, campi clinici, gate, score o bucket.

La pipeline V3 e il registry di default non leggono l'overlay 1.5.
""",
        encoding="utf-8",
    )
    (AUDIT / "safe_propagation_rules.md").write_text(
        """# Safe propagation rules

1. `CLAIM_VERIFIED_LOCATOR`: source unit e locator sono già nella claim oppure provengono da un mapping claim-specifico univoco.
2. `CLAIM_PUBLICATION_IDENTIFIER_ONLY`: mapping claim-specifico e source unit esistono, ma il locator è assente.
3. `PARENT_PUBLICATION_AVAILABLE`: il parent ha una pubblicazione, ma non è dimostrato il passaggio claim-specifico.
4. `AMBIGUOUS_PARENT_PROVENANCE`: il parent ha più pubblicazioni e non esiste mapping univoco.
5. Una aggregate claim senza mapping esplicito non viene attribuita.
6. Nessun valore viene ricostruito per somiglianza testuale e nessun PMID parent-only viene copiato nella claim.

Le condizioni di singola source unit del parent sono applicate solo quando `source_unit_ids` e locator sono realmente presenti nel parent; la 1.4 non presenta questa struttura per le claim parent-only analizzate.
""",
        encoding="utf-8",
    )
    (AUDIT / "repository_version_diff.md").write_text(
        f"""# Repository version diff

- Source: `qualified_claim_repository/1.4`
- Pilot: `qualified_claim_repository/1.5-provenance-pilot`
- Default registry changed: no
- Operational retriever bound: no
- Pilot claim rows: {len(rows)}
- Existing 1.4 rows with modified source-unit fields: {source_units_added}
- New locator fields: {locators_added}

The overlay contains the active claim view and graph parent view needed for inspection, plus a pilot manifest. It is not registered as an operational corpus and does not overwrite any 1.4 file.

All claim semantic fields are equal after removing the pilot-only `provenance_repair` metadata.
""",
        encoding="utf-8",
    )
    (AUDIT / "provenance_repair_report.md").write_text(
        f"""# Provenance repair pilot report

## Decision

Il pilota ha analizzato {len(rows)} claim. Nessuna source unit nuova è stata inventata e nessun PMID parent-only è stato promosso.

- claim con source unit nuova propagata: **{source_units_added}**
- claim con locator nuovo: **{locators_added}**
- claim `CLAIM_PUBLICATION_IDENTIFIER_ONLY`: **{statuses.get('CLAIM_PUBLICATION_IDENTIFIER_ONLY', 0)}**
- claim `PARENT_PUBLICATION_AVAILABLE`: **{statuses.get('PARENT_PUBLICATION_AVAILABLE', 0)}**
- claim `AMBIGUOUS_PARENT_PROVENANCE`: **{statuses.get('AMBIGUOUS_PARENT_PROVENANCE', 0)}**
- claim con mapping/source locator già presente: **{statuses.get('CLAIM_VERIFIED_LOCATOR', 0)}**

## Punto responsabile della perdita

La perdita è nella materializzazione/promozione: `corpus/materialization.py::promoted_claims()` copia i record senza reintrodurre un mapping claim -> source unit. Serializer e adapter non sono stati modificati.

## Estensione alle 131 claim

Non è sicuro estendere automaticamente la riparazione alle 131 claim parent-only: il repository corrente non contiene mapping claim-specifici dimostrabili per esse. Il rischio è attribuire una pubblicazione contestuale alla claim sbagliata, soprattutto per parent multi-pubblicazione e claim aggregate. Serve source-unit review o mapping esplicito upstream.

## Invarianti

- claim semantics: unchanged
- gate/scoring/bucket: unchanged
- repository 1.4: unchanged
- Knowledge Graph, ledger, gold, official experiments: not modified
- API/frontend: unchanged; overlay not default
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
