"""Spiega perché gli hash dei payload ricostruiti divergono dalla baseline.

Un mismatch di hash non va né ignorato né trattato automaticamente come prova
che il contenuto scientifico è cambiato. Le due ipotesi hanno conseguenze
opposte, e distinguerle richiede un esperimento invece di un'inferenza:

* **payload non deterministico** — la sorgente incorpora nel documento un valore
  che cambia a ogni richiesta (un timestamp di risposta, una sezione derivata
  rigenerata). L'hash della baseline non era riproducibile nemmeno il giorno in
  cui è stato scritto, e il mismatch non dice nulla sul contenuto.
* **contenuto cambiato** — la sorgente restituisce oggi un documento diverso.

Il discriminante è scaricare due volte **adesso** lo stesso documento: se i due
hash differiscono fra loro, il payload è non deterministico e l'ipotesi di
contenuto cambiato non è sostenibile per quel formato.

Le richieste avvengono su cache temporanee usa-e-getta: la cache reale non viene
toccata. Nessun testo integrale finisce nel report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline.documents.authorized_cache import (  # noqa: E402
    AuthorizedDocumentCache,
    file_hash,
)

ANALYZER_VERSION = "document-cache-drift-analyzer/1.0"
DEFAULT_REPORT_DIR = _REPO_ROOT / "evaluation" / "document_cache_rebuild"

#: Sezioni che la sorgente genera o ricalcola al momento della risposta. La loro
#: presenza è contesto, non prova: il determinismo lo stabilisce il doppio fetch.
VOLATILE_SECTION_MARKERS = {
    "pmcid": ("<responseDate>",),
    "nct": ('"derivedSection"', '"lastUpdatePostDateStruct"', '"statusVerifiedDate"'),
}

VERDICT_NONDETERMINISTIC = "PAYLOAD_NONDETERMINISTIC"
VERDICT_STABLE = "PAYLOAD_STABLE_ACROSS_FETCHES"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"

#: Perché un mismatch è accettabile senza toccare il contratto del runtime.
EXPLAINED_NONDETERMINISTIC = "EXPLAINED_NONDETERMINISTIC_PAYLOAD"
EXPLAINED_TEXT_UNCHANGED = "EXPLAINED_TEXT_UNCHANGED"
UNEXPLAINED = "UNEXPLAINED"


def double_fetch(kind: str, value: str, relative: str, *, delay_seconds: float) -> dict[str, Any]:
    """Scarica due volte lo stesso documento in cache separate e confronta."""
    hashes: list[str] = []
    sizes: list[int] = []
    markers_found: list[str] = []
    for _ in range(2):
        scratch = Path(tempfile.mkdtemp(prefix="mtb-drift-"))
        try:
            cache = AuthorizedDocumentCache(root=scratch, network=True, delay_seconds=delay_seconds)
            resolver = {"pmid": cache.resolve_pmid, "pmcid": cache.resolve_pmc,
                        "nct": cache.resolve_nct}[kind]
            resolver(value)
            path = scratch / relative
            if not path.is_file():
                return {"identifier_kind": kind, "identifier_value": value,
                        "verdict": VERDICT_INCONCLUSIVE, "reason": "PAYLOAD_NOT_WRITTEN"}
            hashes.append(file_hash(path))
            sizes.append(path.stat().st_size)
            if not markers_found:
                body = path.read_text(encoding="utf-8", errors="replace")
                markers_found = [m for m in VOLATILE_SECTION_MARKERS.get(kind, ()) if m in body]
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    identical = hashes[0] == hashes[1]
    return {
        "identifier_kind": kind,
        "identifier_value": value,
        "relative_path": relative,
        "fetch_1_sha256": hashes[0],
        "fetch_2_sha256": hashes[1],
        "sizes_bytes": sizes,
        "hashes_identical_between_consecutive_fetches": identical,
        "nondeterminism_markers_found": markers_found,
        "verdict": VERDICT_STABLE if identical else VERDICT_NONDETERMINISTIC,
    }


def load_download_results(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "download_results.jsonl"
    if not path.is_file():
        raise SystemExit(f"manca {path}: esegui prima bootstrap_research_document_cache.py")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pick_representatives(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    """Un documento con mismatch per ciascun formato: l'esperimento è per formato."""
    chosen: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        if not row.get("hash_report", {}).get("any_mismatch"):
            continue
        kind = str(row["identifier_kind"])
        if kind in chosen:
            continue
        mismatched = [c["path"] for c in row["hash_report"]["checks"]
                      if c["status"] == "HASH_MISMATCH"]
        if mismatched:
            chosen[kind] = (kind, str(row["identifier_value"]), mismatched[0])
    return [chosen[k] for k in sorted(chosen)]


def text_level_evidence(document_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Per ogni documento: il testo estratto oggi è quello della baseline?

    Non serve conservare il payload originale per rispondere. Gli identificatori
    delle SourceUnit sono ``SU-<sha256(document_id, unit_type, text, offsets)>``:
    se ogni unità ri-parsata oggi compare nell'indice congelato, il testo da cui
    è stata derivata è byte-identico. È una prova più forte del confronto fra
    hash di payload, perché riguarda esattamente ciò che il runtime consuma.
    """
    from backend.research_pipeline import data_access as da
    from backend.research_pipeline.documents import cache_runtime

    cache = cache_runtime.open_read_only()
    manifest = {row["document_id"]: row for row in da.read_jsonl(da.document_manifest_path())}
    index_ids = set(da.load_source_unit_index())

    evidence: dict[str, dict[str, Any]] = {}
    for document_id in document_ids:
        row = manifest.get(document_id)
        if row is None:
            evidence[document_id] = {"status": "NOT_IN_MANIFEST"}
            continue
        try:
            units = cache.source_units_for_record(dict(row))
        except Exception as exc:  # noqa: BLE001 — un parse fallito è un dato
            evidence[document_id] = {"status": "PARSE_FAILED", "error": f"{type(exc).__name__}: {exc}"}
            continue
        produced = {unit["source_unit_id"] for unit in units}
        unmatched = sorted(produced - index_ids)
        evidence[document_id] = {
            "status": "TEXT_UNCHANGED" if not unmatched and produced else "TEXT_CHANGED",
            "source_units_reconstructed": len(produced),
            "source_units_matching_frozen_index": len(produced & index_ids),
            "source_units_not_in_frozen_index": len(unmatched),
        }
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analizza il drift degli hash dei payload.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    args = parser.parse_args(argv)

    rows = load_download_results(args.report_dir)
    fetched = [r for r in rows if r["classification"] == "EXPECTED_AVAILABLE"]

    status_by_kind: Counter[tuple[str, str, str]] = Counter()
    for row in fetched:
        for check in row["hash_report"]["checks"]:
            directory = "/".join(check["path"].split("/")[:-1])
            status_by_kind[(str(row["identifier_kind"]), directory, check["status"])] += 1

    experiments = [double_fetch(kind, value, relative, delay_seconds=args.delay_seconds)
                   for kind, value, relative in pick_representatives(fetched)]

    nondeterministic = {e["identifier_kind"] for e in experiments
                        if e["verdict"] == VERDICT_NONDETERMINISTIC}
    mismatched = [row for row in fetched if row["hash_report"].get("any_mismatch")]
    evidence = text_level_evidence([str(row["document_id"]) for row in mismatched])

    classified: list[dict[str, Any]] = []
    for row in mismatched:
        document_id = str(row["document_id"])
        text_status = evidence.get(document_id, {}).get("status")
        if row["identifier_kind"] in nondeterministic:
            verdict = EXPLAINED_NONDETERMINISTIC
        elif text_status == "TEXT_UNCHANGED":
            verdict = EXPLAINED_TEXT_UNCHANGED
        else:
            verdict = UNEXPLAINED
        classified.append({
            "document_id": document_id,
            "identifier_kind": row["identifier_kind"],
            "verdict": verdict,
            "text_evidence": evidence.get(document_id, {}),
        })

    unexplained = [c["document_id"] for c in classified if c["verdict"] == UNEXPLAINED]

    report = {
        "analyzer_version": ANALYZER_VERSION,
        "documents_examined": len(fetched),
        "hash_status_counts": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in sorted(status_by_kind.items())},
        "documents_with_mismatch": len(mismatched),
        "reproducibility_experiments": experiments,
        "formats_proven_nondeterministic": sorted(nondeterministic),
        "mismatch_classification": classified,
        "mismatch_verdict_counts": dict(Counter(c["verdict"] for c in classified)),
        "unexplained_mismatch_documents": unexplained,
        "unexplained_mismatch_count": len(unexplained),
    }
    path = args.report_dir / "hash_drift_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for experiment in experiments:
        print(f"{experiment['identifier_kind']:6} {experiment['identifier_value']:14} "
              f"{experiment['verdict']:28} markers={experiment['nondeterminism_markers_found']}")
    print(f"formati non deterministici : {report['formats_proven_nondeterministic']}")
    print(f"classificazione mismatch   : {report['mismatch_verdict_counts']}")
    print(f"mismatch non spiegati      : {report['unexplained_mismatch_count']}")
    print(f"report                     : {path.relative_to(_REPO_ROOT).as_posix()}")
    return 0 if not unexplained else 1


if __name__ == "__main__":
    raise SystemExit(main())
