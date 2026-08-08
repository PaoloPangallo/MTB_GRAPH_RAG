"""Ricostruisce la cache documentale letta in sola lettura dalle run LIVE.

**Perché uno script separato.** Il runtime LIVE apre la cache con
``ReadOnlyDocumentCache``, i cui percorsi di rete e di scrittura sollevano: non
può quindi popolarla, ed è una proprietà da preservare, non un limite da
aggirare. Il bootstrap è l'unico punto del progetto in cui la rete è abilitata,
e vive fuori da ``backend/`` proprio perché non faccia parte del runtime.

**Closed document set.** L'insieme dei documenti è definito dal manifest
congelato e versionato (``document_manifest.jsonl``), che questo script legge e
non scrive mai. Non scopre nuove evidenze, non aggiunge identificatori: recupera
esattamente i documenti che il pilot aveva già risolto, negli stessi percorsi
relativi già registrati.

**Riuso dei resolver.** Il fetch, il retry, il rate limit, l'hashing e la
generazione dei percorsi sono quelli di ``AuthorizedDocumentCache`` — la classe
nata per popolare la cache. Riscriverli qui significherebbe avere due
implementazioni della stessa cosa, di cui una non esercitata dal runtime.

**Documenti storicamente non disponibili.** Le righe ``PMC_RESOLUTION_FAILED``
non vengono "riparate": sono il caso reale di documento non ottenibile. Con
``--probe-baseline-unavailable`` lo script verifica se la sorgente si è nel
frattempo aperta, ma lo fa su una cache temporanea usa-e-getta e riporta
``AVAILABILITY_CHANGED_SINCE_BASELINE`` senza scrivere nulla nella cache reale:
il manifest congelato resta l'autorità su cosa il runtime può risolvere.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline import data_access as da  # noqa: E402
from backend.research_pipeline.documents import cache_runtime  # noqa: E402
from backend.research_pipeline.documents.authorized_cache import (  # noqa: E402
    AuthorizedDocumentCache,
    file_hash,
)

BOOTSTRAP_VERSION = "document-cache-bootstrap/1.0"

#: Report versionabili: identificatori, hash, dimensioni e conteggi. Mai testo.
DEFAULT_REPORT_DIR = _REPO_ROOT / "evaluation" / "document_cache_rebuild"

#: Availability del manifest che il pilot ha registrato come non ottenibile.
#: Non sono un guasto del bootstrap: sono un esito documentato della sorgente.
BASELINE_UNAVAILABLE_AVAILABILITY = frozenset({
    "PMC_RESOLUTION_FAILED", "PMC_NOT_FOUND", "PMC_NOT_OPEN",
    "PMID_NOT_FOUND", "NCT_NOT_FOUND", "RESOLUTION_FAILED", "ABSTRACT_EMPTY",
})

CLASS_EXPECTED_AVAILABLE = "EXPECTED_AVAILABLE"
CLASS_EXPECTED_UNAVAILABLE = "EXPECTED_UNAVAILABLE"

HASH_MATCH = "HASH_MATCH"
HASH_MISMATCH = "HASH_MISMATCH"
HASH_NOT_AVAILABLE = "HASH_NOT_AVAILABLE"

OUTCOME_SKIPPED = "SKIPPED_ALREADY_PRESENT"
OUTCOME_DOWNLOADED = "DOWNLOADED"
OUTCOME_FAILED = "FAILED"
OUTCOME_PROBED = "PROBED_NOT_WRITTEN"


def parse_document_id(document_id: str) -> tuple[str, str]:
    """``"pmid:123"`` -> ``("pmid", "123")``. Il prefisso sceglie il resolver."""
    kind, _, value = document_id.partition(":")
    return kind.strip().lower(), value.strip()


def expected_payloads(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Percorsi relativi che il manifest dichiara per questa riga.

    ``metadata_cache_path`` conta quanto ``local_cache_path``: senza il metadata
    la riga resta risolvibile per il runtime, ma la cache non è quella misurata
    nel pilot e il conteggio dei file non tornerebbe.
    """
    paths = (row.get("local_cache_path"), row.get("metadata_cache_path"))
    return tuple(str(p) for p in paths if p)


def classify(row: Mapping[str, Any]) -> str:
    availability = str(row.get("availability") or "")
    if not expected_payloads(row) or availability in BASELINE_UNAVAILABLE_AVAILABILITY:
        return CLASS_EXPECTED_UNAVAILABLE
    return CLASS_EXPECTED_AVAILABLE


def payload_state(root: Path, row: Mapping[str, Any]) -> str:
    """``PRESENT`` solo se **ogni** payload atteso esiste e non è vuoto."""
    expected = expected_payloads(row)
    if not expected:
        return "NOT_EXPECTED"
    present = [rel for rel in expected if (root / rel).is_file() and (root / rel).stat().st_size > 0]
    if len(present) == len(expected):
        return "PRESENT"
    return "PARTIAL" if present else "MISSING"


def compare_hash(root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    """Confronta gli hash del manifest congelato con i file appena scritti.

    Un mismatch non viene corretto né nascosto: è il segnale che la sorgente ha
    restituito qualcosa di diverso dal 2026-08-06, e va spiegato prima di
    dichiarare la cache compatibile.
    """
    checks: list[dict[str, Any]] = []
    for relative, expected in (
        (row.get("local_cache_path"), row.get("content_hash")),
        (row.get("metadata_cache_path"), row.get("metadata_hash")),
    ):
        if not relative:
            continue
        path = root / relative
        if not path.is_file():
            checks.append({"path": relative, "status": HASH_NOT_AVAILABLE, "reason": "FILE_MISSING"})
            continue
        actual = file_hash(path)
        if not expected:
            checks.append({"path": relative, "status": HASH_NOT_AVAILABLE,
                           "reason": "NO_BASELINE_HASH", "actual_hash": actual,
                           "size_bytes": path.stat().st_size})
            continue
        checks.append({
            "path": relative,
            "status": HASH_MATCH if actual == expected else HASH_MISMATCH,
            "expected_hash": expected,
            "actual_hash": actual,
            "size_bytes": path.stat().st_size,
        })
    return {"checks": checks,
            "any_mismatch": any(c["status"] == HASH_MISMATCH for c in checks)}


def forget_bootstrap_manifest_entry(cache: AuthorizedDocumentCache, document_id: str) -> bool:
    """Rimuove una voce dal manifest **del bootstrap**, non da quello congelato.

    ``AuthorizedDocumentCache`` considera già risolto ciò che compare nel proprio
    manifest e restituisce il record senza riscaricare. Se il payload è stato
    cancellato, quella scorciatoia produrrebbe un successo apparente su un file
    inesistente: la voce va dimenticata perché il refetch avvenga davvero.
    """
    manifest = cache.manifest_path
    if not manifest.is_file():
        return False
    kept = [line for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("document_id") != document_id]
    manifest.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
    return True


@dataclass(frozen=True)
class FetchOutcome:
    document_id: str
    identifier_kind: str
    identifier_value: str
    classification: str
    baseline_availability: str
    outcome: str
    observed_availability: str | None = None
    availability_changed: bool = False
    expected_paths: tuple[str, ...] = ()
    payload_state_before: str = ""
    payload_state_after: str = ""
    bytes_written: int = 0
    hash_report: Mapping[str, Any] = field(default_factory=dict)
    resolution_attempts: tuple[Mapping[str, Any], ...] = ()
    error: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "document_id": self.document_id,
            "identifier_kind": self.identifier_kind,
            "identifier_value": self.identifier_value,
            "classification": self.classification,
            "baseline_availability": self.baseline_availability,
            "outcome": self.outcome,
            "observed_availability": self.observed_availability,
            "availability_changed_since_baseline": self.availability_changed,
            "expected_paths": list(self.expected_paths),
            "payload_state_before": self.payload_state_before,
            "payload_state_after": self.payload_state_after,
            "bytes_written": self.bytes_written,
            "hash_report": dict(self.hash_report),
            "resolution_attempts": [dict(a) for a in self.resolution_attempts],
            "duration_seconds": round(self.duration_seconds, 3),
        }
        if self.error:
            payload["error"] = self.error
        return payload


def _resolver_for(cache: AuthorizedDocumentCache, kind: str) -> Callable[[str], dict[str, Any]] | None:
    return {"pmid": cache.resolve_pmid,
            "pmcid": cache.resolve_pmc,
            "nct": cache.resolve_nct}.get(kind)


def _total_bytes(root: Path, relatives: Iterable[str]) -> int:
    return sum((root / rel).stat().st_size for rel in relatives if (root / rel).is_file())


def fetch_document(cache: AuthorizedDocumentCache, row: Mapping[str, Any], *,
                   force: bool = False) -> FetchOutcome:
    """Recupera un documento del closed set. Idempotente: presente -> nessuna rete."""
    document_id = str(row["document_id"])
    kind, value = parse_document_id(document_id)
    expected = expected_payloads(row)
    baseline = str(row.get("availability") or "")
    before = payload_state(cache.root, row)
    common = {
        "document_id": document_id, "identifier_kind": kind, "identifier_value": value,
        "classification": classify(row), "baseline_availability": baseline,
        "expected_paths": expected, "payload_state_before": before,
    }

    if before == "PRESENT" and not force:
        return FetchOutcome(**common, outcome=OUTCOME_SKIPPED, payload_state_after=before,
                            hash_report=compare_hash(cache.root, row),
                            bytes_written=_total_bytes(cache.root, expected))

    resolver = _resolver_for(cache, kind)
    if resolver is None:
        return FetchOutcome(**common, outcome=OUTCOME_FAILED, payload_state_after=before,
                            error=f"nessun resolver per il prefisso {kind!r}")

    # Il payload manca: la voce nel manifest del bootstrap va dimenticata,
    # altrimenti il resolver la considera già risolta e non scarica.
    forget_bootstrap_manifest_entry(cache, document_id)

    started = time.monotonic()
    try:
        record = resolver(value)
    except Exception as exc:  # noqa: BLE001 — un fetch fallito è un dato del report
        return FetchOutcome(**common, outcome=OUTCOME_FAILED, payload_state_after=payload_state(cache.root, row),
                            error=f"{type(exc).__name__}: {exc}",
                            duration_seconds=time.monotonic() - started)

    after = payload_state(cache.root, row)
    observed = str(record.get("availability") or "")
    return FetchOutcome(
        **common,
        outcome=OUTCOME_DOWNLOADED if after == "PRESENT" else OUTCOME_FAILED,
        observed_availability=observed,
        availability_changed=bool(baseline and observed and observed != baseline),
        payload_state_after=after,
        bytes_written=_total_bytes(cache.root, expected),
        hash_report=compare_hash(cache.root, row),
        resolution_attempts=tuple(record.get("resolution_attempts") or ()),
        duration_seconds=time.monotonic() - started,
    )


def probe_baseline_unavailable(row: Mapping[str, Any], *, delay_seconds: float) -> FetchOutcome:
    """Verifica se una riga storicamente non risolta lo è ancora, senza scrivere.

    Il resolver gira su una cache temporanea che viene distrutta: la cache reale
    resta allineata al manifest congelato, e un documento che oggi fosse
    disponibile non entrerebbe comunque nel corpus senza una decisione esplicita.
    """
    document_id = str(row["document_id"])
    kind, value = parse_document_id(document_id)
    baseline = str(row.get("availability") or "")
    common = {
        "document_id": document_id, "identifier_kind": kind, "identifier_value": value,
        "classification": classify(row), "baseline_availability": baseline,
        "expected_paths": expected_payloads(row), "payload_state_before": "NOT_EXPECTED",
        "payload_state_after": "NOT_EXPECTED",
    }
    scratch = Path(tempfile.mkdtemp(prefix="mtb-cache-probe-"))
    started = time.monotonic()
    try:
        probe_cache = AuthorizedDocumentCache(root=scratch, network=True, delay_seconds=delay_seconds)
        resolver = _resolver_for(probe_cache, kind)
        if resolver is None:
            return FetchOutcome(**common, outcome=OUTCOME_FAILED,
                                error=f"nessun resolver per il prefisso {kind!r}")
        record = resolver(value)
        observed = str(record.get("availability") or "")
        return FetchOutcome(
            **common, outcome=OUTCOME_PROBED, observed_availability=observed,
            availability_changed=observed not in BASELINE_UNAVAILABLE_AVAILABILITY,
            resolution_attempts=tuple(record.get("resolution_attempts") or ()),
            duration_seconds=time.monotonic() - started,
        )
    except Exception as exc:  # noqa: BLE001
        return FetchOutcome(**common, outcome=OUTCOME_FAILED,
                            error=f"{type(exc).__name__}: {exc}",
                            duration_seconds=time.monotonic() - started)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def build_inventory(rows: Sequence[Mapping[str, Any]], manifest_path: Path) -> dict[str, Any]:
    """Inventario del closed set. Solo identificatori, stati e conteggi."""
    documents = []
    for row in rows:
        kind, value = parse_document_id(str(row["document_id"]))
        identifiers = row.get("identifiers") or {}
        documents.append({
            "document_id": row["document_id"],
            "identifier_kind": kind,
            "identifier_value": value,
            "pmid": identifiers.get("pmid"),
            "pmcid": identifiers.get("pmcid"),
            "doi": identifiers.get("doi"),
            "nct": identifiers.get("nct"),
            "availability": row.get("availability"),
            "content_type": row.get("content_type"),
            "local_cache_path": row.get("local_cache_path"),
            "metadata_cache_path": row.get("metadata_cache_path"),
            "content_hash": row.get("content_hash"),
            "metadata_hash": row.get("metadata_hash"),
            "license_status": row.get("license_status"),
            "retrieved_at": row.get("retrieved_at"),
            "source": row.get("source"),
            "historical_errors": row.get("errors") or [],
            "candidate_ids": row.get("candidate_ids") or [],
            "classification": classify(row),
            "expected_payloads": list(expected_payloads(row)),
        })

    def tally(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for document in documents:
            counts[str(document[key])] = counts.get(str(document[key]), 0) + 1
        return dict(sorted(counts.items()))

    expected_files: dict[str, int] = {}
    for document in documents:
        for relative in document["expected_payloads"]:
            top = relative.split("/")[0] if "/" in relative else relative
            group = "/".join(relative.split("/")[:2]) if relative.count("/") >= 2 else top
            expected_files[group] = expected_files.get(group, 0) + 1

    return {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "manifest_path": manifest_path.relative_to(_REPO_ROOT).as_posix(),
        "manifest_sha256": cache_runtime._file_sha256(manifest_path),
        "manifest_document_count": len(documents),
        "counts_by_identifier_kind": tally("identifier_kind"),
        "counts_by_availability": tally("availability"),
        "counts_by_classification": tally("classification"),
        "expected_payload_files_by_directory": dict(sorted(expected_files.items())),
        "expected_available_count": sum(1 for d in documents if d["classification"] == CLASS_EXPECTED_AVAILABLE),
        "expected_unavailable_count": sum(1 for d in documents if d["classification"] == CLASS_EXPECTED_UNAVAILABLE),
        "documents": documents,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(outcomes: Sequence[FetchOutcome], root: Path) -> dict[str, Any]:
    available, reasons = cache_runtime.validate_cache(root)
    fetched = [o for o in outcomes if o.classification == CLASS_EXPECTED_AVAILABLE]
    mismatches = [o.document_id for o in fetched if o.hash_report.get("any_mismatch")]
    return {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "cache_root_redacted": cache_runtime.redact_path(root),
        "expected_available": len(fetched),
        "downloaded": sum(1 for o in fetched if o.outcome == OUTCOME_DOWNLOADED),
        "cache_hits_skipped": sum(1 for o in fetched if o.outcome == OUTCOME_SKIPPED),
        "failed": sum(1 for o in fetched if o.outcome == OUTCOME_FAILED),
        "unexpected_missing": [o.document_id for o in fetched if o.payload_state_after != "PRESENT"],
        "expected_unavailable": sum(1 for o in outcomes if o.classification == CLASS_EXPECTED_UNAVAILABLE),
        "availability_changed_since_baseline": [
            o.document_id for o in outcomes if o.availability_changed
        ],
        "hash_mismatch_documents": mismatches,
        "hash_mismatch_count": len(mismatches),
        "validate_cache_available": available,
        "validate_cache_reason_codes": list(reasons),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ricostruisce la cache documentale read-only usata dalle run LIVE.")
    parser.add_argument("--cache-root", type=Path, default=None,
                        help="Root della cache. Default: quella risolta dal runtime.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--audit-only", action="store_true",
                        help="Produce solo l'inventario del manifest, senza rete.")
    parser.add_argument("--force", action="store_true",
                        help="Riscarica anche i payload gia presenti.")
    parser.add_argument("--probe-baseline-unavailable", action="store_true",
                        help="Verifica se i documenti storicamente non risolti lo sono ancora.")
    parser.add_argument("--delay-seconds", type=float, default=0.34,
                        help="Pausa fra le richieste. Default 0.34 (~3 req/s, limite NCBI).")
    parser.add_argument("--only", action="append", default=None,
                        help="Limita a document_id specifici. Ripetibile.")
    args = parser.parse_args(argv)

    manifest_path = da.document_manifest_path()
    rows = da.read_jsonl(manifest_path)
    if args.only:
        wanted = set(args.only)
        rows = [row for row in rows if row["document_id"] in wanted]

    inventory = build_inventory(rows, manifest_path)
    inventory_path = args.report_dir / "manifest_inventory.json"
    write_json(inventory_path, inventory)
    print(f"manifest            : {inventory['manifest_document_count']} documenti")
    print(f"  attesi disponibili: {inventory['expected_available_count']}")
    print(f"  attesi assenti    : {inventory['expected_unavailable_count']}")
    print(f"inventario          : {inventory_path.relative_to(_REPO_ROOT).as_posix()}")

    if args.audit_only:
        return 0

    root = (args.cache_root.expanduser().resolve() if args.cache_root
            else cache_runtime.cache_path())
    print(f"cache root          : {root}")
    cache = AuthorizedDocumentCache(root=root, network=True, delay_seconds=args.delay_seconds)

    outcomes: list[FetchOutcome] = []
    for index, row in enumerate(rows, start=1):
        document_id = str(row["document_id"])
        if classify(row) == CLASS_EXPECTED_UNAVAILABLE:
            if args.probe_baseline_unavailable:
                outcome = probe_baseline_unavailable(row, delay_seconds=args.delay_seconds)
            else:
                outcome = FetchOutcome(
                    document_id=document_id, identifier_kind=parse_document_id(document_id)[0],
                    identifier_value=parse_document_id(document_id)[1],
                    classification=CLASS_EXPECTED_UNAVAILABLE,
                    baseline_availability=str(row.get("availability") or ""),
                    outcome=OUTCOME_SKIPPED, payload_state_before="NOT_EXPECTED",
                    payload_state_after="NOT_EXPECTED",
                )
        else:
            outcome = fetch_document(cache, row, force=args.force)
        outcomes.append(outcome)
        print(f"[{index:2}/{len(rows)}] {document_id:22} {outcome.outcome}")

    results_path = args.report_dir / "download_results.jsonl"
    write_jsonl(results_path, (o.to_dict() for o in outcomes))

    summary = summarize(outcomes, root)
    summary_path = args.report_dir / "download_summary.json"
    write_json(summary_path, summary)

    print("")
    print(f"scaricati           : {summary['downloaded']}")
    print(f"gia presenti        : {summary['cache_hits_skipped']}")
    print(f"falliti             : {summary['failed']}")
    print(f"mancanti inattesi   : {len(summary['unexpected_missing'])}")
    print(f"hash mismatch       : {summary['hash_mismatch_count']}")
    print(f"validate_cache      : {summary['validate_cache_available']} {summary['validate_cache_reason_codes']}")
    print(f"report              : {results_path.relative_to(_REPO_ROOT).as_posix()}")

    return 0 if summary["validate_cache_available"] and not summary["unexpected_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
