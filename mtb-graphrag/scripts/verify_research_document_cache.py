"""Verifica che la cache ricostruita sia quella che il runtime LIVE si aspetta.

Ricostruire i payload non basta. Gli identificatori delle SourceUnit sono
derivati dal contenuto — ``SU-<sha256(document_id, unit_type, text, offsets)>`` —
e i bundle congelati citano quegli identificatori per nome. Se il testo estratto
oggi differisce anche di un carattere da quello del 2026-08-06, gli ID cambiano,
``paper_selection`` non risolve alcuna unità e ogni bundle viene escluso con
``TEXT_NOT_AVAILABLE_IN_CACHE``: la run LIVE arriverebbe allo stage 8 senza
paper, senza che nulla segnali il perché.

Per questo la verifica non si ferma a ``validate_cache()``. Misura l'unica cosa
che conta davvero: quante delle SourceUnit **citate dai bundle** vengono
effettivamente risolte con testo dalla cache appena ricostruita.

Sola lettura, come il runtime. Nessuna rete, nessuna scrittura nella cache, e
nessun testo integrale negli artefatti prodotti.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline import data_access as da  # noqa: E402
from backend.research_pipeline.documents import cache_runtime  # noqa: E402
from backend.research_pipeline.documents.live_resolution import DocumentRuntime  # noqa: E402

VERIFIER_VERSION = "document-cache-verifier/1.0"
DEFAULT_REPORT_DIR = _REPO_ROOT / "evaluation" / "document_cache_rebuild"

#: Prefissi da coprire nella sonda runtime: una sonda che tocca solo PubMed non
#: direbbe nulla su JATS e ClinicalTrials, che usano parser diversi.
PROBE_KINDS = ("pmid", "pmcid", "nct")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def reconstruct(
    runtime: DocumentRuntime, rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    """Ri-parsa le SourceUnit di ogni documento risolvibile. Nessun testo esportato."""
    per_document: list[dict[str, Any]] = []
    units_by_id: dict[str, dict[str, Any]] = {}

    for row in rows:
        document_id = str(row["document_id"])
        relative = row.get("local_cache_path")
        resolved = bool(relative) and (runtime.cache.root / relative).is_file()
        entry: dict[str, Any] = {
            "document_id": document_id,
            "availability": row.get("availability"),
            "local_cache_path": relative,
            "payload_present": resolved,
            "source_unit_count": 0,
            "unit_types": {},
            "with_text": 0,
            "without_text": 0,
            "parsers": {},
            "parse_error": None,
        }
        if not resolved:
            entry["parse_error"] = "PAYLOAD_NOT_PRESENT" if relative else "NO_LOCAL_CACHE_PATH"
            per_document.append(entry)
            continue
        try:
            produced = runtime.cache.source_units_for_record(dict(row))
        except Exception as exc:  # noqa: BLE001 — un parse fallito è un dato
            entry["parse_error"] = f"{type(exc).__name__}: {exc}"
            per_document.append(entry)
            continue

        types: dict[str, int] = {}
        parsers: dict[str, int] = {}
        for unit in produced:
            units_by_id[unit["source_unit_id"]] = unit
            types[str(unit.get("unit_type"))] = types.get(str(unit.get("unit_type")), 0) + 1
            key = f"{unit.get('parser')}@{unit.get('parser_version')}"
            parsers[key] = parsers.get(key, 0) + 1
        entry.update({
            "source_unit_count": len(produced),
            "unit_types": dict(sorted(types.items())),
            "parsers": dict(sorted(parsers.items())),
            "with_text": sum(1 for u in produced if (u.get("text") or "").strip()),
            "without_text": sum(1 for u in produced if not (u.get("text") or "").strip()),
        })
        per_document.append(entry)

    summary = {
        "verifier_version": VERIFIER_VERSION,
        "documents_examined": len(per_document),
        "documents_parsed": sum(1 for d in per_document if d["parse_error"] is None and d["payload_present"]),
        "documents_with_parse_error": sum(1 for d in per_document if d["parse_error"] and d["payload_present"]),
        "documents_without_payload": sum(1 for d in per_document if not d["payload_present"]),
        "source_units_reconstructed": len(units_by_id),
        "source_units_with_text": sum(1 for u in units_by_id.values() if (u.get("text") or "").strip()),
        "schema_complete": sum(
            1 for u in units_by_id.values()
            if u.get("source_unit_id") and u.get("document_id") and u.get("unit_type")
            and (u.get("text") or "").strip()
        ),
    }
    return per_document, {"summary": summary, "documents": per_document}, units_by_id


def compare_with_index(units_by_id: Mapping[str, dict], bundles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Confronta gli ID ricostruiti con l'indice congelato e con i bundle.

    L'intersezione globale con l'indice descrive la fedeltà della ricostruzione;
    la copertura per bundle descrive se il runtime funzionerà. Sono domande
    diverse: un indice coperto al 90% con i bundle scoperti darebbe comunque una
    pipeline muta allo stage 8.
    """
    index = da.load_source_unit_index()
    index_ids = set(index)
    rebuilt_ids = set(units_by_id)

    bundle_rows: list[dict[str, Any]] = []
    for bundle in bundles:
        wanted = list(bundle.get("source_unit_ids") or [])
        resolved = [uid for uid in wanted
                    if uid in units_by_id and (units_by_id[uid].get("text") or "").strip()]
        bundle_rows.append({
            "bundle_id": bundle.get("bundle_id"),
            "bundle_type": bundle.get("bundle_type"),
            "document_id": bundle.get("document_id"),
            "requested_source_units": len(wanted),
            "resolved_with_text": len(resolved),
            "missing": sorted(set(wanted) - set(resolved)),
            "fully_resolved": len(resolved) == len(wanted) and bool(wanted),
            "text_available": bool(resolved),
        })

    by_kind: dict[str, dict[str, int]] = {}
    for row in bundle_rows:
        kind = str(row["document_id"]).split(":")[0]
        slot = by_kind.setdefault(kind, {"bundles": 0, "fully_resolved": 0,
                                         "text_available": 0, "requested": 0, "resolved": 0})
        slot["bundles"] += 1
        slot["fully_resolved"] += int(row["fully_resolved"])
        slot["text_available"] += int(row["text_available"])
        slot["requested"] += row["requested_source_units"]
        slot["resolved"] += row["resolved_with_text"]

    return {
        "verifier_version": VERIFIER_VERSION,
        "source_unit_ids_in_index": len(index_ids),
        "source_unit_ids_reconstructed": len(rebuilt_ids),
        "intersection": len(index_ids & rebuilt_ids),
        "missing_from_reconstruction": len(index_ids - rebuilt_ids),
        "new_from_reconstruction": len(rebuilt_ids - index_ids),
        "text_available_count": sum(1 for u in units_by_id.values() if (u.get("text") or "").strip()),
        "bundle_coverage": {
            "bundles_total": len(bundle_rows),
            "bundles_fully_resolved": sum(1 for r in bundle_rows if r["fully_resolved"]),
            "bundles_with_text": sum(1 for r in bundle_rows if r["text_available"]),
            "bundles_without_text": sum(1 for r in bundle_rows if not r["text_available"]),
            "source_units_requested": sum(r["requested_source_units"] for r in bundle_rows),
            "source_units_resolved": sum(r["resolved_with_text"] for r in bundle_rows),
            "by_identifier_kind": {k: by_kind[k] for k in sorted(by_kind)},
        },
        "bundles": bundle_rows,
    }


def runtime_probe(runtime: DocumentRuntime, bundles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Esercita stage 6 e 7 sul percorso reale, un bundle per tipo di sorgente."""
    chosen: dict[str, Mapping[str, Any]] = {}
    for bundle in bundles:
        kind = str(bundle.get("document_id", "")).split(":")[0]
        if kind in PROBE_KINDS and kind not in chosen:
            chosen[kind] = bundle

    associations = [{
        "candidate_id": bundle.get("candidate_id") or f"probe-{kind}",
        "available_bundles": [dict(bundle)],
    } for kind, bundle in chosen.items()]

    resolution = runtime.resolve(associations)
    units = runtime.load_units(resolution)

    documents = [{
        "document_id": doc.document_id,
        "availability": doc.availability,
        "resolved": doc.resolved,
        "cache_hit": doc.cache_hit,
        "document_type": doc.document_type,
        "reason_codes": list(doc.reason_codes),
        "content_hash": doc.content_hash,
    } for doc in resolution.documents]

    per_kind = []
    for kind, bundle in chosen.items():
        wanted = list(bundle.get("source_unit_ids") or [])
        with_text = [uid for uid in wanted
                     if (units.units_by_id.get(uid, {}).get("text") or "").strip()]
        per_kind.append({
            "identifier_kind": kind,
            "document_id": bundle.get("document_id"),
            "bundle_id": bundle.get("bundle_id"),
            "requested_source_units": len(wanted),
            "source_units_with_text": len(with_text),
            "text_available": bool(with_text),
            "max_text_length": max(
                (len(units.units_by_id.get(uid, {}).get("text") or "") for uid in with_text),
                default=0,
            ),
        })

    return {
        "verifier_version": VERIFIER_VERSION,
        "document_runtime_open": "SUCCEEDED",
        "cache_path_redacted": resolution.cache_path_redacted,
        "manifest_hash": resolution.manifest_hash,
        "network_fetch_used": False,
        "stage_6_documents": documents,
        "stage_6_resolved_count": sum(1 for d in documents if d["resolved"]),
        "stage_6_unavailable_count": sum(1 for d in documents if not d["resolved"]),
        "stage_7_documents_parsed": units.documents_parsed,
        "stage_7_documents_failed": [dict(f) for f in units.documents_failed],
        "stage_7_units_total": len(units.units_by_id),
        "stage_7_units_with_text": units.with_text,
        "probes": per_kind,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica la cache documentale ricostruita.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)

    root = cache_runtime.cache_path()
    available, reasons = cache_runtime.validate_cache(root)
    descriptor = cache_runtime.describe(root).to_dict()
    validation = {
        "verifier_version": VERIFIER_VERSION,
        "cache_root_redacted": cache_runtime.redact_path(root),
        "validate_cache_available": available,
        "validate_cache_reason_codes": list(reasons),
        "descriptor": descriptor,
    }
    write_json(args.report_dir / "cache_validation.json", validation)
    print(f"validate_cache      : {available} {reasons}")
    print(f"document_count      : {descriptor['document_count']} / manifest_rows {descriptor['manifest_rows']}")

    if not available:
        print("cache non utilizzabile: verifica interrotta.")
        return 1

    # Verifica della cache: sola lettura, nessuna acquisizione di rete.
    runtime = DocumentRuntime.open_read_only_research()
    rows = da.read_jsonl(da.document_manifest_path())
    bundles = da.read_jsonl(da.evidence_bundles_path())

    per_document, reconstruction, units_by_id = reconstruct(runtime, rows)
    write_jsonl(args.report_dir / "document_resolution_results.jsonl", per_document)
    write_json(args.report_dir / "source_unit_reconstruction.json", reconstruction)
    print(f"documenti parsati   : {reconstruction['summary']['documents_parsed']}")
    print(f"SourceUnit ricostr. : {reconstruction['summary']['source_units_reconstructed']}"
          f" (con testo {reconstruction['summary']['source_units_with_text']})")

    comparison = compare_with_index(units_by_id, bundles)
    write_json(args.report_dir / "source_unit_index_comparison.json", comparison)
    print(f"indice congelato    : {comparison['source_unit_ids_in_index']}")
    print(f"intersezione        : {comparison['intersection']}")
    print(f"mancanti            : {comparison['missing_from_reconstruction']}")
    print(f"nuovi               : {comparison['new_from_reconstruction']}")
    coverage = comparison["bundle_coverage"]
    print(f"bundle con testo    : {coverage['bundles_with_text']}/{coverage['bundles_total']}"
          f"  (unita {coverage['source_units_resolved']}/{coverage['source_units_requested']})")

    probe = runtime_probe(runtime, bundles)
    write_json(args.report_dir / "live_runtime_probe.json", probe)
    print(f"sonda runtime       : stage6 risolti {probe['stage_6_resolved_count']}"
          f"/{len(probe['stage_6_documents'])}, stage7 con testo {probe['stage_7_units_with_text']}")

    return 0 if coverage["bundles_with_text"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
