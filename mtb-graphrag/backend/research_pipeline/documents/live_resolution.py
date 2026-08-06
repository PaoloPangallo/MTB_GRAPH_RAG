"""Document Resolution e materializzazione delle SourceUnit, eseguite durante la run.

Due stage che il runtime precedente non eseguiva affatto: enumerava i
``document_id`` già presenti nei bundle del retrieval e li marcava
``replayed: true``. Qui i documenti vengono realmente cercati nella cache
autorizzata, e le SourceUnit realmente ri-parsate dal loro contenuto.

**Nessun fetch di rete.** La cache è aperta in sola lettura da
``cache_runtime.ReadOnlyDocumentCache``, i cui percorsi di rete sollevano
un'eccezione. Un documento assente resta assente: ``DOCUMENT_UNAVAILABLE`` è un
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
from typing import Any, Iterable, Mapping

from .cache_runtime import ReadOnlyDocumentCache, describe, open_read_only, redact_path

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
            "network_fetch_used": False,
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

    cache: ReadOnlyDocumentCache
    manifest_by_document_id: Mapping[str, Mapping[str, Any]]
    descriptor: Mapping[str, Any]

    @property
    def manifest_hash(self) -> str | None:
        return self.descriptor.get("manifest_hash")

    @classmethod
    def open(cls) -> "DocumentRuntime":
        """Apre la cache o solleva ``DocumentCacheUnavailable``. Nessun ripiego."""
        from backend.research_pipeline import data_access as da

        cache = open_read_only()
        manifest = da.read_jsonl(da.document_manifest_path())
        return cls(
            cache=cache,
            manifest_by_document_id={row["document_id"]: row for row in manifest},
            descriptor=describe(cache.root).to_dict(),
        )

    def resolve(self, associations: Iterable[Mapping[str, Any]]) -> DocumentResolution:
        return resolve_documents(
            associations, self.manifest_by_document_id, self.cache,
            manifest_hash=self.manifest_hash,
        )

    def load_units(self, resolution: DocumentResolution) -> SourceUnitBundle:
        return load_source_units(resolution, self.manifest_by_document_id, self.cache)
