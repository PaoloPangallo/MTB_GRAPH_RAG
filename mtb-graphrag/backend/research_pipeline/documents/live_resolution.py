"""Document Resolution e materializzazione delle SourceUnit, eseguite durante la run.

Due stage che il runtime precedente non eseguiva affatto: enumerava i
``document_id`` già presenti nei bundle del retrieval e li marcava
``replayed: true``. Qui i documenti vengono realmente cercati nella cache
autorizzata, e le SourceUnit realmente ri-parsate dal loro contenuto.

In REPLAY la cache è aperta in sola lettura da
``cache_runtime.ReadOnlyDocumentCache`` e la rete è vietata. In LIVE la stessa
risoluzione usa ``AuthorizedDocumentCache`` in modalità cache-first: un miss
può chiamare esclusivamente i resolver ufficiali e persistere lo snapshot prima
del parsing. Un documento assente resta assente: ``DOCUMENT_UNAVAILABLE`` è un
esito, non una condizione da aggirare.

**Il testo resta qui.** ``SourceUnitBundle`` tiene due proiezioni separate:
``units_by_id`` con ``text``, che non lascia il backend ed è ciò su cui il
validatore verifica la letteralità di una quote; e ``previews``, con locatore,
hash, tipo e una preview troncata — la sola forma che raggiunge ledger e API.
Tenerle separate nella struttura dati, e non nel punto di serializzazione,
significa che esporre il testo richiederebbe un errore deliberato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable, Mapping

from .authorized_cache import AuthorizedDocumentCache
from .cache_runtime import ReadOnlyDocumentCache, cache_path, describe, open_read_only, redact_path

#: Lunghezza della preview testuale mostrata in UI. Sufficiente a riconoscere il
#: passaggio, insufficiente a ricostruire il documento.
PREVIEW_CHARS = 180

RESOLVER_VERSION = "live-document-resolution/1.0"
LOADER_VERSION = "live-source-unit-loader/1.0"

#: Availability del manifest che comporta contenuto testuale ri-parsabile.
_TEXT_AVAILABILITY: frozenset[str] = frozenset({
    "ABSTRACT_AVAILABLE", "PMC_XML_AVAILABLE", "LOCAL_PDF_AVAILABLE",
})

#: I record ClinicalTrials sono ``METADATA_ONLY`` nel vocabolario del resolver ma
#: hanno testo strutturato (brief summary, descrizione, condizioni). Trattarli
#: come privi di testo escluderebbe l'intera classe dei trial dalla selezione.
_TRIAL_PREFIX = "nct:"


def _document_type(document_id: str, availability: str) -> str:
    if document_id.startswith(_TRIAL_PREFIX):
        return "CLINICAL_TRIAL_RECORD"
    if availability == "PMC_XML_AVAILABLE":
        return "FULL_TEXT_ARTICLE"
    if availability == "ABSTRACT_AVAILABLE":
        return "ABSTRACT"
    if availability == "LOCAL_PDF_AVAILABLE":
        return "LOCAL_PDF"
    return "METADATA_RECORD"


@dataclass(frozen=True)
class ResolvedDocument:
    """Esito della risoluzione di un singolo documento."""

    document_id: str
    bundle_id: str
    candidate_id: str
    availability: str
    resolved: bool
    cache_hit: bool
    document_type: str
    source: str | None
    metadata_only: bool
    abstract_available: bool
    full_text_available: bool
    content_hash: str | None
    reason_codes: tuple[str, ...]
    lineage: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "bundle_id": self.bundle_id,
            "candidate_id": self.candidate_id,
            "availability": self.availability,
            "resolved": self.resolved,
            "cache_hit": self.cache_hit,
            "document_type": self.document_type,
            "source": self.source,
            "metadata_only": self.metadata_only,
            "abstract_available": self.abstract_available,
            "full_text_available": self.full_text_available,
            "content_hash": self.content_hash,
            "reason_codes": list(self.reason_codes),
            "lineage": dict(self.lineage),
        }


@dataclass(frozen=True)
class DocumentResolution:
    documents: tuple[ResolvedDocument, ...]
    cache_path_redacted: str
    manifest_hash: str | None

    @property
    def cache_hits(self) -> int:
        return sum(1 for doc in self.documents if doc.cache_hit)

    @property
    def cache_misses(self) -> int:
        return sum(1 for doc in self.documents if not doc.cache_hit)

    @property
    def records_by_document_id(self) -> dict[str, ResolvedDocument]:
        return {doc.document_id: doc for doc in self.documents}

    @property
    def records_by_bundle_id(self) -> dict[str, ResolvedDocument]:
        return {doc.bundle_id: doc for doc in self.documents}

    @property
    def network_fetch_count(self) -> int:
        return sum(
            1 for doc in self.documents
            if doc.lineage.get("retrieval_mode") == "LIVE_FETCH" and not doc.cache_hit
        )

    def to_preview(self) -> dict[str, Any]:
        return {
            "documents": [doc.to_dict() for doc in self.documents],
            "resolved_count": sum(1 for doc in self.documents if doc.resolved),
            "unavailable_count": sum(1 for doc in self.documents if not doc.resolved),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_path_redacted": self.cache_path_redacted,
            "manifest_hash": self.manifest_hash,
            "resolver_version": RESOLVER_VERSION,
            "network_fetch_used": self.network_fetch_count > 0,
            "network_fetch_count": self.network_fetch_count,
        }


def resolve_documents(
    associations: Iterable[Mapping[str, Any]],
    manifest_by_document_id: Mapping[str, Mapping[str, Any]],
    cache: ReadOnlyDocumentCache,
    *,
    manifest_hash: str | None = None,
) -> DocumentResolution:
    """Risolve ogni documento citato dai bundle, leggendo solo la cache."""
    resolved: list[ResolvedDocument] = []
    seen: set[tuple[str, str]] = set()

    for association in associations:
        candidate_id = association.get("candidate_id", "")
        for bundle in association.get("available_bundles", []) or []:
            document_id = bundle.get("document_id") or ""
            key = (candidate_id, bundle.get("bundle_id") or "")
            if key in seen:
                continue
            seen.add(key)

            record = manifest_by_document_id.get(document_id)
            if record is None:
                resolved.append(ResolvedDocument(
                    document_id=document_id, bundle_id=bundle.get("bundle_id") or "",
                    candidate_id=candidate_id, availability="NOT_IN_MANIFEST",
                    resolved=False, cache_hit=False, document_type="UNKNOWN",
                    source=None, metadata_only=False, abstract_available=False,
                    full_text_available=False, content_hash=None,
                    reason_codes=("DOCUMENT_UNAVAILABLE", "DOCUMENT_NOT_IN_MANIFEST"),
                    lineage={"resolver_version": RESOLVER_VERSION},
                ))
                continue

            availability = str(record.get("availability") or "UNKNOWN")
            relative = record.get("local_cache_path")
            cache_hit = bool(relative) and (cache.root / relative).is_file()

            reason_codes: tuple[str, ...]
            if not relative:
                reason_codes = ("DOCUMENT_UNAVAILABLE", "NO_LOCAL_CACHE_PATH")
            elif not cache_hit:
                reason_codes = ("DOCUMENT_UNAVAILABLE", "CACHE_MISS")
            else:
                reason_codes = ("DOCUMENT_RESOLVED_FROM_CACHE",)

            is_trial = document_id.startswith(_TRIAL_PREFIX)
            has_text = cache_hit and (availability in _TEXT_AVAILABILITY or is_trial)

            resolved.append(ResolvedDocument(
                document_id=document_id,
                bundle_id=bundle.get("bundle_id") or "",
                candidate_id=candidate_id,
                availability=availability,
                resolved=cache_hit,
                cache_hit=cache_hit,
                document_type=_document_type(document_id, availability),
                source=record.get("source"),
                metadata_only=availability == "METADATA_ONLY" and not is_trial,
                abstract_available=availability == "ABSTRACT_AVAILABLE",
                full_text_available=availability == "PMC_XML_AVAILABLE",
                content_hash=record.get("content_hash"),
                reason_codes=reason_codes if has_text or not cache_hit
                             else (*reason_codes, "NO_TEXT_FOR_AVAILABILITY"),
                lineage={
                    "resolver_version": RESOLVER_VERSION,
                    "manifest_hash": manifest_hash,
                    "retrieved_at": record.get("retrieved_at"),
                    "license_status": record.get("license_status"),
                },
            ))

    return DocumentResolution(
        documents=tuple(resolved),
        cache_path_redacted=redact_path(cache.root),
        manifest_hash=manifest_hash,
    )


def _manifest_hash(path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _live_manifest_rows(cache: AuthorizedDocumentCache) -> dict[str, dict[str, Any]]:
    if not cache.manifest_path.is_file():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for line in cache.manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["document_id"]] = row
    return rows


def _live_descriptor(cache: AuthorizedDocumentCache, rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    text_availability = {"ABSTRACT_AVAILABLE", "PMC_XML_AVAILABLE", "LOCAL_PDF_AVAILABLE"}
    return {
        "document_cache_available": True,
        "cache_path_redacted": redact_path(cache.root),
        "cache_version": cache.resolver_version,
        "reason_codes": [],
        "manifest_hash": _manifest_hash(cache.manifest_path),
        "manifest_rows": len(rows),
        "document_count": len(rows),
        "documents_with_text": sum(1 for row in rows.values() if row.get("availability") in text_availability),
        "documents_unavailable": sum(1 for row in rows.values() if row.get("availability") not in text_availability),
        "source_unit_count": 0,
        "retrieval_mode": "CACHE_FIRST_API_ON_MISS",
    }


def resolve_live_documents(
    associations: Iterable[Mapping[str, Any]],
    cache: AuthorizedDocumentCache,
    manifest_by_document_id: dict[str, Mapping[str, Any]],
) -> DocumentResolution:
    """Resolve GCA provenance through the writable authorized cache."""
    resolved: list[ResolvedDocument] = []
    seen: set[tuple[str, str]] = set()
    for association in associations:
        candidate_id = association.get("candidate_id", "")
        for bundle in association.get("available_bundles", []) or []:
            requested_id = bundle.get("document_id") or ""
            key = (candidate_id, bundle.get("bundle_id") or requested_id)
            if key in seen:
                continue
            seen.add(key)
            item = bundle.get("provenance_identifier") or {}
            record = cache.resolve_live_identifier(dict(item))
            actual_id = record.get("document_id") or requested_id
            manifest_by_document_id[actual_id] = record
            availability = str(record.get("availability") or "UNKNOWN")
            is_trial = actual_id.startswith("nct:")
            has_text = bool(record.get("local_cache_path")) and (
                availability in _TEXT_AVAILABILITY or is_trial
            )
            cache_hit = bool(record.get("cache_hit"))
            reasons = ["CACHE_HIT" if cache_hit else "CACHE_MISS"]
            if not cache_hit and record.get("retrieval_mode") == "LIVE_FETCH":
                reasons.extend(["DOCUMENT_FETCH_STARTED", "DOCUMENT_FETCH_SUCCEEDED"] if has_text else ["DOCUMENT_FETCH_FAILED"])
            if record.get("degradation_reason"):
                reasons.append(str(record["degradation_reason"]))
            if has_text:
                reasons.append("DOCUMENT_RESOLVED")
            else:
                reasons.append("DOCUMENT_UNAVAILABLE")
            resolved.append(ResolvedDocument(
                document_id=actual_id, bundle_id=bundle.get("bundle_id") or requested_id,
                candidate_id=candidate_id, availability=availability, resolved=has_text,
                cache_hit=cache_hit, document_type=_document_type(actual_id, availability),
                source=record.get("source"), metadata_only=availability == "METADATA_ONLY" and not is_trial,
                abstract_available=availability == "ABSTRACT_AVAILABLE",
                full_text_available=availability == "PMC_XML_AVAILABLE",
                content_hash=record.get("content_hash"), reason_codes=tuple(reasons),
                lineage={
                    "resolver_version": record.get("resolver_version") or cache.resolver_version,
                    "requested_document_id": requested_id,
                    "retrieved_at": record.get("retrieved_at"),
                    "retrieval_mode": "CACHE_HIT" if cache_hit else (record.get("retrieval_mode") or "LIVE_FETCH"),
                    "snapshot_retrieval_mode": record.get("retrieval_mode"),
                    "retrieval_source": record.get("source"),
                    "raw_payload_hash": record.get("content_hash"),
                    "payload_size": record.get("payload_size", 0),
                    "cache_path": record.get("local_cache_path"),
                    "derived_pmcid": record.get("derived_pmcid"),
                    "degradation_reason": record.get("degradation_reason"),
                },
            ))
    return DocumentResolution(
        documents=tuple(resolved), cache_path_redacted=redact_path(cache.root),
        manifest_hash=_manifest_hash(cache.manifest_path),
    )


@dataclass(frozen=True)
class SourceUnitBundle:
    """Unità con testo per il backend, proiezione redatta per tutto il resto."""

    units_by_id: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    previews: tuple[dict[str, Any], ...] = ()
    documents_parsed: int = 0
    documents_failed: tuple[dict[str, Any], ...] = ()

    @property
    def with_text(self) -> int:
        return sum(1 for unit in self.units_by_id.values() if (unit.get("text") or "").strip())

    def to_preview(self, requested_ids: Iterable[str] | None = None) -> dict[str, Any]:
        wanted = set(requested_ids) if requested_ids is not None else None
        previews = [p for p in self.previews if wanted is None or p["source_unit_id"] in wanted]
        return {
            "source_units": previews,
            "source_unit_count": len(previews),
            "with_exact_text": sum(1 for p in previews if p["exact_text_available"]),
            "without_text": sum(1 for p in previews if not p["exact_text_available"]),
            "documents_parsed": self.documents_parsed,
            "documents_failed": list(self.documents_failed),
            "loader_version": LOADER_VERSION,
            "text_never_exposed": True,
            "preview_chars": PREVIEW_CHARS,
        }


def _preview_for(unit: Mapping[str, Any]) -> dict[str, Any]:
    """Proiezione pubblica di una SourceUnit. ``text`` non compare mai."""
    text = str(unit.get("text") or "")
    has_text = bool(text.strip())
    return {
        "source_unit_id": unit.get("source_unit_id"),
        "document_id": unit.get("document_id"),
        "unit_type": unit.get("unit_type"),
        "locator": {
            "section": unit.get("section"),
            "paragraph_index": unit.get("paragraph_index"),
            "sentence_index": unit.get("sentence_index"),
            "char_start": unit.get("char_start"),
            "char_end": unit.get("char_end"),
            "page": unit.get("page"),
            "confidence": unit.get("locator_confidence"),
        },
        "index": unit.get("sentence_index") if unit.get("sentence_index") is not None
                 else unit.get("paragraph_index"),
        "exact_text_available": has_text,
        "length": len(text),
        "text_preview": (text[:PREVIEW_CHARS] + "…") if len(text) > PREVIEW_CHARS else text,
        "content_hash": unit.get("content_hash"),
        "selectable": has_text,
        "reason_codes": [] if has_text else ["SOURCE_UNIT_TEXT_UNAVAILABLE"],
        "lineage": {
            "parser": unit.get("parser"),
            "parser_version": unit.get("parser_version"),
            "loader_version": LOADER_VERSION,
        },
    }


def load_source_units(
    resolution: DocumentResolution,
    manifest_by_document_id: Mapping[str, Mapping[str, Any]],
    cache: ReadOnlyDocumentCache,
) -> SourceUnitBundle:
    """Ri-parsa dalla cache le SourceUnit dei documenti effettivamente risolti."""
    units: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    parsed = 0

    for document_id in sorted({doc.document_id for doc in resolution.documents if doc.resolved}):
        record = manifest_by_document_id.get(document_id)
        if record is None:
            continue
        try:
            produced = cache.source_units_for_record(dict(record))
        except Exception as exc:  # noqa: BLE001 — un parse fallito è un dato, non un crash
            failures.append({
                "document_id": document_id,
                "reason_codes": ["SOURCE_UNIT_PARSE_FAILED"],
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        parsed += 1
        for unit in produced:
            units[unit["source_unit_id"]] = unit

    previews = tuple(_preview_for(unit) for unit in units.values())
    return SourceUnitBundle(
        units_by_id=units,
        previews=previews,
        documents_parsed=parsed,
        documents_failed=tuple(failures),
    )


@dataclass(frozen=True)
class DocumentRuntime:
    """Cache aperta, manifest indicizzato e descrittore, per una singola run.

    Aperta una volta all'inizio della run e passata agli stage 6 e 7: riaprirla
    per stage significherebbe che i due potrebbero leggere stati diversi della
    stessa cache, e la ``manifest_hash`` mostrata non garantirebbe più nulla.
    """

    cache: Any
    manifest_by_document_id: dict[str, Mapping[str, Any]]
    descriptor: Mapping[str, Any]
    network_enabled: bool = False

    @property
    def manifest_hash(self) -> str | None:
        return self.descriptor.get("manifest_hash")

    @classmethod
    def open(cls) -> "DocumentRuntime":
        """Runtime documentale **canonico**: cache-first, API autorizzate sul miss.

        È il solo runtime aperto dal percorso operativo. Prima questo nome
        designava la cache in sola lettura, e il runtime canonico si chiamava
        ``open_live``: i due erano invertiti rispetto a quale dovesse essere il
        default, ed è il genere di dettaglio da cui nasce un percorso sbagliato
        preso per distrazione.
        """
        cache = AuthorizedDocumentCache(root=cache_path(), network=True)
        manifest = _live_manifest_rows(cache)
        return cls(
            cache=cache, manifest_by_document_id=dict(manifest),
            descriptor=_live_descriptor(cache, manifest), network_enabled=True,
        )

    @classmethod
    def open_live(cls) -> "DocumentRuntime":
        """Nome storico del runtime canonico. Alias di ``open``.

        Resta perché compare in script e probe già scritti. Non aggiunge un
        percorso: ne nomina uno.
        """
        return cls.open()

    @classmethod
    def open_read_only_research(cls) -> "DocumentRuntime":
        """RESEARCH / REGRESSION ONLY — cache in sola lettura, rete vietata.

        Serve agli harness che devono mostrare che un percorso senza rete
        produce esattamente ciò che produsse allora. Non è il default e non è
        raggiungibile dall'API: chiamarlo è una dichiarazione esplicita di
        volere il comportamento storico.
        """
        from backend.research_pipeline import data_access as da

        cache = open_read_only()
        manifest = da.read_jsonl(da.document_manifest_path())
        return cls(
            cache=cache,
            manifest_by_document_id={row["document_id"]: row for row in manifest},
            descriptor=describe(cache.root).to_dict(),
            network_enabled=False,
        )

    def resolve(self, associations: Iterable[Mapping[str, Any]]) -> DocumentResolution:
        if self.network_enabled:
            return resolve_live_documents(associations, self.cache, self.manifest_by_document_id)
        return resolve_documents(
            associations, self.manifest_by_document_id, self.cache,
            manifest_hash=self.manifest_hash,
        )

    def load_units(self, resolution: DocumentResolution) -> SourceUnitBundle:
        return load_source_units(resolution, self.manifest_by_document_id, self.cache)
