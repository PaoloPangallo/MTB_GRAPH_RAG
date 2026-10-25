"""Authorized, cached document resolution for the offline grounding pilot.

The cache is deliberately outside Git. This module writes only to the configured
cache root and never changes the V3 runtime or the historical repository.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .parsers import JatsXmlParser, PdfDocumentParser, PubMedAbstractParser
from .models import SourceUnit

PMID_RE = re.compile(r"^\d+$")
NCT_RE = re.compile(r"^NCT\d{8}$", re.I)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
URL_RE = re.compile(r"^https?://", re.I)
# A temporary transport outage is not permanent source absence. One hour keeps
# retries bounded across runs; each revalidation uses the existing endpoint and
# infrastructure-attempt limits. Positive and terminal-negative records do not expire.
TRANSIENT_NEGATIVE_CACHE_TTL_SECONDS = 3600


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize_source_unit_occurrence_ids(
    document_id: str,
    units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign deterministic, document-scoped identities to parser occurrences.

    Parsers may legitimately emit identical text at distinct structural
    occurrences.  Their content-derived IDs are therefore finalized only once
    the complete canonical parser order is available.
    """
    finalized: list[dict[str, Any]] = []
    for final_ordinal, source in enumerate(units):
        unit = dict(source)
        content = {key: value for key, value in unit.items()
                   if key not in {"source_unit_id", "content_hash"}}
        digest = stable_hash({"document_id": document_id,
                              "final_ordinal": final_ordinal,
                              "canonical_sourceunit_content": content})
        unit["source_unit_id"] = f"SU-{digest[:24]}"
        finalized.append(unit)
    return finalized


def cache_root_from_env() -> Path:
    return Path(os.environ.get("DOCUMENT_GROUNDING_CACHE", "data_cache/document_grounding"))


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _keyed_identifier(item: dict[str, Any]) -> tuple[str, str] | None:
    for kind in ("pmid", "pmcid", "doi", "nct", "url"):
        value = _norm(item.get(kind))
        if value:
            if kind in {"pmid", "pmcid", "nct"}:
                value = value.upper()
            if kind == "doi":
                value = value.lower().removeprefix("https://doi.org/")
            return kind, value
    return None


def expand_identifier(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Split compound PMID/NCT fields while preserving the raw candidate value elsewhere."""
    if not isinstance(item, dict):
        return []
    for kind in ("pmid", "pmcid", "doi", "nct", "url"):
        raw = _norm(item.get(kind))
        if not raw:
            continue
        parts = [part.strip() for part in re.split(r"[;,]", raw) if part.strip()] if kind in {"pmid", "pmcid", "nct"} else [raw]
        expanded = []
        for part in parts:
            if kind == "pmid" and DOI_RE.fullmatch(part):
                expanded.append({
                    "doi": part,
                    "original_identifier_type": "pmid",
                    "identifier_status": "DOI_LIKE_IN_PMID_FIELD",
                    **({"scope": item["scope"]} if item.get("scope") else {}),
                })
            else:
                expanded.append({kind: part, **({"scope": item["scope"]} if item.get("scope") else {})})
        return expanded
    return []

def load_candidates(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


@dataclass
class IdentifierInventory:
    candidates: list[dict[str, Any]]

    def build(self) -> dict[str, Any]:
        unique: dict[str, set[str]] = defaultdict(set)
        raw_counts: Counter[str] = Counter()
        candidate_counts: Counter[str] = Counter()
        malformed: list[dict[str, Any]] = []
        unrecognized: list[dict[str, Any]] = []
        candidate_cardinality: list[dict[str, Any]] = []
        same_type_conflicts: list[dict[str, Any]] = []
        for candidate in self.candidates:
            identifiers = candidate.get("document_identifiers") or []
            by_type: dict[str, set[str]] = defaultdict(set)
            for raw_item in identifiers:
                expanded = expand_identifier(raw_item)
                if not expanded:
                    unrecognized.append({"candidate_id": candidate.get("candidate_id"), "value": raw_item})
                    continue
                for item in expanded:
                    keyed = _keyed_identifier(item)
                    if not keyed:
                        unrecognized.append({"candidate_id": candidate.get("candidate_id"), "value": item})
                        continue
                    kind, value = keyed
                    raw_counts[kind] += 1
                    unique[kind].add(value)
                    candidate_counts[kind] += 1
                    by_type[kind].add(value)
                    valid = ((kind == "pmid" and PMID_RE.fullmatch(value)) or
                             (kind == "pmcid" and value.upper().startswith("PMC") and value[3:].isdigit()) or
                             (kind == "doi" and DOI_RE.fullmatch(value)) or
                             (kind == "nct" and NCT_RE.fullmatch(value)) or
                             (kind == "url" and URL_RE.fullmatch(value)))
                    if not valid:
                        malformed.append({"candidate_id": candidate.get("candidate_id"), "type": kind, "value": value})
            for kind, values in by_type.items():
                if len(values) > 1:
                    same_type_conflicts.append({"candidate_id": candidate.get("candidate_id"), "type": kind, "values": sorted(values)})
            candidate_cardinality.append({
                "candidate_id": candidate.get("candidate_id"),
                "identifier_count": len(identifiers),
                "pmid_count": len(by_type.get("pmid", set())),
                "pmcid_count": len(by_type.get("pmcid", set())),
                "doi_count": len(by_type.get("doi", set())),
                "nct_count": len(by_type.get("nct", set())),
                "url_count": len(by_type.get("url", set())),
                "has_identifier": bool(identifiers),
                "has_multiple_documents": len(identifiers) > 1,
            })
        linked = sum(row["has_identifier"] for row in candidate_cardinality)
        return {
            "candidate_count": len(self.candidates),
            "candidate_with_identifier": linked,
            "candidate_without_identifier": len(self.candidates) - linked,
            "candidate_with_multiple_documents": sum(row["has_multiple_documents"] for row in candidate_cardinality),
            "unique_identifiers": {kind: sorted(values) for kind, values in sorted(unique.items())},
            "unique_counts": {kind: len(values) for kind, values in sorted(unique.items())},
            "raw_identifier_occurrences": dict(raw_counts),
            "duplicate_occurrences": {kind: raw_counts[kind] - len(values) for kind, values in unique.items()},
            "malformed_identifiers": malformed,
            "unrecognized_identifiers": unrecognized,
            "candidate_identifier_conflicts": same_type_conflicts,
            "candidate_cardinality": candidate_cardinality,
        }


def select_authorized_pilot(candidates: list[dict[str, Any]], limit: int = 40) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select strata before resolution; availability is never used as a criterion."""
    def text(candidate: dict[str, Any]) -> str:
        return json.dumps(candidate, ensure_ascii=False, sort_keys=True).lower()

    def has(candidate: dict[str, Any], token: str) -> bool:
        return token.lower() in text(candidate)

    strata = [
        ("EGFR_L858R", lambda c: has(c, "EGFR") and has(c, "L858R") and has(c, "osimertinib")),
        ("FGFR2_fusion_iCCA", lambda c: has(c, "FGFR2") and (has(c, "fusion") or has(c, "BICC1"))),
        ("ALK_G1202R", lambda c: has(c, "ALK") and has(c, "G1202R")),
        ("sensitivity", lambda c: "sensitivity" in (c.get("direction") or "").lower() or "response" in (c.get("direction") or "").lower()),
        ("resistance", lambda c: "resistance" in (c.get("direction") or "").lower()),
        ("diagnostic", lambda c: c.get("predicate") == "has_companion_diagnostic"),
        ("regimen", lambda c: bool(c.get("regimen"))),
        ("aggregate", lambda c: "aggregate" in text(c) or "multiple" in text(c)),
        ("one_pmid", lambda c: sum(1 for i in c.get("document_identifiers", []) if i.get("pmid")) == 1),
        ("multiple_pmid", lambda c: sum(1 for i in c.get("document_identifiers", []) if i.get("pmid")) > 1),
        ("nct", lambda c: any(i.get("nct") for i in c.get("document_identifiers", []))),
        ("no_document", lambda c: not c.get("document_identifiers")),
        ("therapeutic", lambda c: bool(c.get("interventions"))),
    ]
    ordered = sorted(candidates, key=lambda c: c["candidate_id"])
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_strata: dict[str, list[str]] = defaultdict(list)
    for name, predicate in strata:
        for candidate in ordered:
            if candidate["candidate_id"] not in selected_ids and predicate(candidate):
                selected.append(candidate)
                selected_ids.add(candidate["candidate_id"])
                selected_strata[name].append(candidate["candidate_id"])
                break
    for candidate in ordered:
        if len(selected) >= limit:
            break
        if candidate["candidate_id"] not in selected_ids:
            selected.append(candidate)
            selected_ids.add(candidate["candidate_id"])
    criteria = {
        "limit": limit,
        "selection_order": [name for name, _ in strata],
        "availability_not_used": True,
        "selected_count": len(selected),
        "selected_strata": dict(selected_strata),
        "candidate_ids": [c["candidate_id"] for c in selected],
    }
    return selected, criteria


class AuthorizedDocumentCache:
    """Local cache with optional network resolution; cache paths are relative."""
    resolver_version = "authorized-cache/1.2"

    def __init__(self, root: str | Path | None = None, network: bool = True, delay_seconds: float = 0.34):
        self.root = Path(root) if root else cache_root_from_env()
        self.network = network
        self.delay_seconds = delay_seconds
        for relative in ("pubmed/metadata", "pubmed/abstracts", "pmc/xml", "clinical_trials", "local_pdf", "manifests", "errors"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifests" / "documents.jsonl"
        self.user_agent = os.environ.get("DOCUMENT_GROUNDING_USER_AGENT", "MTB-Evidence-Research/1.0 contact=local")

    def _request(self, url: str) -> tuple[bytes | None, dict[str, Any]]:
        if not self.network:
            return None, {"kind": "network_disabled", "url": url}
        last_error: dict[str, Any] = {}
        for attempt in range(1, 4):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "*/*"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = response.read()
                    time.sleep(self.delay_seconds)
                    return payload, {"attempt": attempt, "status": response.status, "url": url}
            except urllib.error.HTTPError as exc:
                last_error = {"attempt": attempt, "kind": "http", "status": exc.code, "url": url}
                if exc.code in {400, 404, 410}:
                    break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = {"attempt": attempt, "kind": "transient", "error": str(exc), "url": url}
            time.sleep(min(2 ** attempt, 8))
        return None, last_error

    def _write_payload(self, relative: str, payload: bytes) -> tuple[str, str]:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return str(Path(relative).as_posix()), file_hash(path)

    def _record(self, record: dict[str, Any]) -> dict[str, Any]:
        record.setdefault("cache_hit", False)
        record.setdefault("retrieval_mode", "LIVE_FETCH" if self.network else "CACHE_ONLY")
        record.setdefault("resolver_version", self.resolver_version)
        payload_sizes = []
        for field in ("local_cache_path", "metadata_cache_path"):
            relative = record.get(field)
            if relative and (self.root / relative).is_file():
                payload_sizes.append((self.root / relative).stat().st_size)
        record.setdefault("payload_size", max(payload_sizes, default=0))
        with self.manifest_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def _cached_manifest(self, document_id: str) -> dict[str, Any] | None:
        if not self.manifest_path.exists():
            return None
        found = None
        for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("document_id") == document_id:
                    found = row
        return found

    def _negative_cache_revalidation(self, record: dict[str, Any] | None) -> dict[str, Any] | None:
        """Describe an expired, payload-free PubMed transport failure, if any."""
        if (not self.network or not record or record.get('availability') != 'RESOLUTION_FAILED'
                or record.get('local_cache_path') or record.get('metadata_cache_path')):
            return None
        attempts = record.get('resolution_attempts') or []
        if not attempts or any(attempt.get('status') in {400, 404, 410} for attempt in attempts):
            return None
        transient = any(attempt.get('kind') == 'transient' or (
            isinstance(attempt.get('status'), int) and (
                attempt['status'] in {408, 425, 429} or 500 <= attempt['status'] < 600))
            for attempt in attempts)
        if not transient:
            return None
        try:
            retrieved = datetime.fromisoformat(str(record.get('retrieved_at', '')).replace('Z', '+00:00'))
        except ValueError:
            return None
        if retrieved.tzinfo is None or time.time() - retrieved.timestamp() < TRANSIENT_NEGATIVE_CACHE_TTL_SECONDS:
            return None
        return {'previous_record_sha256': stable_hash(record),
                'previous_availability': record['availability'],
                'previous_retrieved_at': record['retrieved_at'],
                'ttl_seconds': TRANSIENT_NEGATIVE_CACHE_TTL_SECONDS,
                'reason': 'EXPIRED_TRANSIENT_TRANSPORT_FAILURE'}

    @staticmethod
    def _cache_record_payload(
        root: Path, record: dict[str, Any], *, require_hash: bool = False
    ) -> Path | None:
        """Return a validated local payload path, or ``None``.

        A manifest row is not evidence of availability by itself: the indexed
        path must resolve to a readable file and, when supplied, its digest must
        agree with the recorded content hash.  Absolute paths are rejected so
        cache records cannot escape their declared root.
        """
        relative = record.get("local_cache_path")
        if not relative or record.get("availability") != "PMC_XML_AVAILABLE":
            return None
        candidate = Path(str(relative))
        if candidate.is_absolute():
            return None
        path = (root / candidate).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return None
        if not path.is_file():
            return None
        expected = record.get("content_hash")
        if require_hash and not expected:
            return None
        if expected and file_hash(path) != expected:
            return None
        return path

    def _authoritative_cached_manifest(self, document_id: str) -> dict[str, Any] | None:
        """Read an explicitly configured sibling cache without network or writes.

        This is deliberately opt-in via ``RESEARCH_DOCUMENT_AUTHORITATIVE_CACHE_ROOT``;
        it prevents an offline evaluation from silently depending on a stale
        primary index while keeping the resolver's fail-closed behaviour.
        """
        configured = os.environ.get("RESEARCH_DOCUMENT_AUTHORITATIVE_CACHE_ROOT", "").strip()
        if not configured:
            return None
        authoritative_root = Path(configured).expanduser().resolve()
        if authoritative_root == self.root.resolve():
            return None
        manifest = authoritative_root / "manifests" / "documents.jsonl"
        if not manifest.is_file():
            return None
        found = None
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("document_id") == document_id:
                    found = row
        if not found:
            return None
        payload = self._cache_record_payload(authoritative_root, found, require_hash=True)
        if payload is None:
            return None
        result = dict(found)
        result["local_cache_path"] = str(payload)
        result["cache_hit"] = True
        result["retrieval_mode"] = "CACHE_ONLY"
        result["cache_root_identity"] = str(authoritative_root)
        result.setdefault("resolver_version", self.resolver_version)
        return result

    @staticmethod
    def _pubmed_xml_fields(payload: bytes, requested_pmid: str | None = None) -> tuple[dict[str, Any], str | None]:
        root = ET.fromstring(payload)
        articles = root.findall(".//PubmedArticle")
        article = None
        requested = _norm(requested_pmid) if requested_pmid else None
        for candidate in articles:
            node = candidate.find("./MedlineCitation/PMID")
            if node is None:
                for identifier in candidate.findall("./PubmedData/ArticleIdList/ArticleId"):
                    if identifier.attrib.get("IdType", "").lower() in {"pubmed", "pmid"}:
                        node = identifier
                        break
            if requested and node is not None and _norm("".join(node.itertext())) == requested:
                article = candidate
                break
        if article is None and requested and len(articles) > 1:
            # A multi-record response without the requested identity is not
            # safe to interpret as the requested document.
            return {}, None
        if article is None and requested and len(articles) == 1:
            # A single record is still accepted for backwards-compatible
            # minimal PubMed fixtures that omit the Medline PMID node.
            article = articles[0]
        if article is None and articles:
            article = articles[0]
        if article is None:
            return {}, None
        def first_text(path: str) -> str | None:
            node = article.find(path)
            return "".join(node.itertext()).strip() if node is not None else None
        title = first_text(".//ArticleTitle")
        abstract_nodes = article.findall(".//Abstract/AbstractText")
        sections = [{"label": node.attrib.get("Label"), "text": "".join(node.itertext()).strip()} for node in abstract_nodes]
        abstract = "\n".join(item["text"] for item in sections if item["text"]) or None
        pmcid = None
        main_article_ids = article.find("./PubmedData/ArticleIdList")
        for node in main_article_ids.findall("./ArticleId") if main_article_ids is not None else ():
            if node.attrib.get("IdType", "").lower() == "pmc":
                pmcid = (node.text or "").strip().upper()
        doi = None
        for node in article.findall("./PubmedData/ArticleIdList/ArticleId"):
            if node.attrib.get("IdType", "").lower() == "doi":
                doi = (node.text or "").strip().lower()
        publication_types = ["".join(n.itertext()).strip() for n in article.findall(".//PublicationType")]
        return {"title": title, "abstract": abstract, "abstract_sections": sections,
                "pmcid": pmcid, "doi": doi, "publication_types": publication_types}, pmcid

    @staticmethod
    def inline_abstract(record: dict[str, Any]) -> str | None:
        """Return abstract text materialized in a manifest record, if any."""
        abstract = record.get("abstract")
        if isinstance(abstract, str) and abstract.strip():
            return abstract
        sections = record.get("abstract_sections")
        if isinstance(sections, list):
            value = "\n".join(
                str(section.get("text") or "").strip()
                for section in sections
                if isinstance(section, dict) and str(section.get("text") or "").strip()
            ).strip()
            if value:
                return value
        return None

    def has_text_payload(self, record: dict[str, Any]) -> bool:
        """Whether a cache record exposes a real payload to the parser."""
        if record.get("availability") == "ABSTRACT_AVAILABLE" and self.inline_abstract(record):
            return True
        relative = record.get("local_cache_path")
        return bool(relative and (self.root / relative).is_file())

    def resolve_pmid(self, pmid: str, *, force_refresh: bool = False) -> dict[str, Any]:
        pmid = _norm(pmid)
        document_id = f"pmid:{pmid}"
        cached = None if force_refresh else self._cached_manifest(document_id)
        revalidation = self._negative_cache_revalidation(cached)
        if cached and revalidation is None:
            cached = dict(cached)
            cached["cache_hit"] = True
            return cached
        record: dict[str, Any] = {"document_id": document_id, "identifiers": {"pmid": pmid},
                                  "candidate_ids": [], "availability": "RESOLUTION_FAILED",
                                  "content_type": None, "local_cache_path": None, "source": "NCBI E-utilities",
                                  "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                                  "content_hash": None, "license_status": "PUBLIC_METADATA_ABSTRACT",
                                  "resolution_attempts": [], "errors": []}
        if revalidation is not None:
            record['negative_cache_revalidation'] = revalidation
        if not PMID_RE.fullmatch(pmid):
            record["availability"] = "PMID_NOT_FOUND"
            record["errors"].append({"kind": "malformed_pmid"})
            return self._record(record)
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + urllib.parse.quote(pmid)
        summary_payload, summary_attempt = self._request(summary_url)
        record["resolution_attempts"].append(summary_attempt)
        if summary_payload:
            try:
                data = json.loads(summary_payload.decode("utf-8"))
                result = data.get("result", {}).get(pmid, {})
                if result:
                    record.update({"title": result.get("title"), "authors": result.get("authors"),
                                   "journal": result.get("fulljournalname"), "year": result.get("pubdate"),
                                   "language": result.get("lang"), "publication_types": result.get("pubtype", [])})
                    metadata_relative, metadata_hash = self._write_payload(f"pubmed/metadata/{pmid}.json", summary_payload)
                    record["metadata_cache_path"] = metadata_relative
                    record["metadata_hash"] = metadata_hash
                    record["availability"] = "METADATA_ONLY"
                else:
                    record["availability"] = "PMID_NOT_FOUND"
            except (ValueError, UnicodeDecodeError) as exc:
                record["errors"].append({"kind": "metadata_parse", "error": str(exc)})
        if self.network and record["availability"] != "PMID_NOT_FOUND":
            abstract_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=" + urllib.parse.quote(pmid)
            abstract_payload, abstract_attempt = self._request(abstract_url)
            record["resolution_attempts"].append(abstract_attempt)
            if abstract_payload:
                try:
                    fields, pmcid = self._pubmed_xml_fields(abstract_payload, pmid)
                    record.update(fields)
                    if pmcid:
                        record["identifiers"]["pmcid"] = pmcid
                    if fields.get("doi"):
                        record["identifiers"]["doi"] = fields["doi"]
                    if fields.get("abstract"):
                        relative, digest = self._write_payload(f"pubmed/abstracts/{pmid}.xml", abstract_payload)
                        record["local_cache_path"] = relative
                        record["content_type"] = "application/xml"
                        record["content_hash"] = digest
                        record["availability"] = "ABSTRACT_AVAILABLE"
                    else:
                        record["availability"] = "ABSTRACT_EMPTY"
                except (ET.ParseError, UnicodeDecodeError) as exc:
                    record["errors"].append({"kind": "abstract_parse", "error": str(exc)})
        return self._record(record)

    def resolve_pmc(self, pmcid: str) -> dict[str, Any]:
        pmcid = _norm(pmcid).upper()
        document_id = f"pmcid:{pmcid}"
        cached = self._cached_manifest(document_id)
        if cached and self._cache_record_payload(self.root, cached):
            cached["cache_hit"] = True
            return cached
        authoritative = self._authoritative_cached_manifest(document_id)
        if authoritative:
            return authoritative
        record = {"document_id": document_id, "identifiers": {"pmcid": pmcid}, "candidate_ids": [],
                  "availability": "PMC_RESOLUTION_FAILED", "content_type": None, "local_cache_path": None,
                  "source": "NCBI PMC OAI", "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "content_hash": None, "license_status": None, "resolution_attempts": [], "errors": []}
        if not re.fullmatch(r"PMC\d+", pmcid):
            record["availability"] = "PMC_NOT_FOUND"
            return self._record(record)
        url = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&metadataPrefix=pmc&identifier=oai:pubmedcentral.nih.gov:" + pmcid[3:]
        payload, attempt = self._request(url)
        record["resolution_attempts"].append(attempt)
        if not payload:
            record["availability"] = "PMC_NOT_FOUND" if attempt.get("status") == 404 else "PMC_RESOLUTION_FAILED"
            return self._record(record)
        if b"<error" in payload[:2000].lower():
            record["availability"] = "PMC_NOT_OPEN"
            record["errors"].append({"kind": "pmc_oai_error"})
            return self._record(record)
        relative, digest = self._write_payload(f"pmc/xml/{pmcid}.xml", payload)
        record.update({"availability": "PMC_XML_AVAILABLE", "content_type": "application/xml",
                       "local_cache_path": relative, "content_hash": digest,
                       "license_status": "PMC_ACCESSIBLE"})
        return self._record(record)

    def resolve_nct(self, nct: str) -> dict[str, Any]:
        nct = _norm(nct).upper()
        document_id = f"nct:{nct}"
        cached = self._cached_manifest(document_id)
        if cached:
            cached["cache_hit"] = True
            return cached
        record = {"document_id": document_id, "identifiers": {"nct": nct}, "candidate_ids": [],
                  "availability": "RESOLUTION_FAILED", "content_type": None, "local_cache_path": None,
                  "source": "ClinicalTrials.gov API v2", "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "content_hash": None, "license_status": "PUBLIC_METADATA", "resolution_attempts": [], "errors": []}
        if not NCT_RE.fullmatch(nct):
            record["availability"] = "NCT_NOT_FOUND"
            return self._record(record)
        url = "https://clinicaltrials.gov/api/v2/studies/" + urllib.parse.quote(nct)
        payload, attempt = self._request(url)
        record["resolution_attempts"].append(attempt)
        if not payload:
            record["availability"] = "NCT_NOT_FOUND" if attempt.get("status") == 404 else "RESOLUTION_FAILED"
            return self._record(record)
        relative, digest = self._write_payload(f"clinical_trials/{nct}.json", payload)
        try:
            data = json.loads(payload.decode("utf-8"))
            protocol = data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})
            record.update({"availability": "METADATA_ONLY", "content_type": "application/json",
                           "local_cache_path": relative, "content_hash": digest,
                           "title": ident.get("briefTitle"), "brief_summary": protocol.get("descriptionModule", {}).get("briefSummary"),
                           "detailed_description": protocol.get("descriptionModule", {}).get("detailedDescription"),
                           "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
                           "interventions": protocol.get("armsInterventionsModule", {}).get("interventions", []),
                           "study_type": design.get("studyType"), "phase": design.get("phases", []),
                           "recruitment_status": status.get("overallStatus"), "last_update": status.get("lastUpdatePostDateStruct")})
        except (ValueError, UnicodeDecodeError) as exc:
            record["errors"].append({"kind": "trial_parse", "error": str(exc)})
        return self._record(record)

    def resolve_local_pdf(self, pdf_path: str | Path, identifier: dict[str, Any]) -> dict[str, Any]:
        """Index an explicitly supplied PDF only when an identifier mapping exists."""
        keyed = _keyed_identifier(identifier)
        if not keyed:
            raise ValueError("local PDF requires PMID, PMCID, DOI, NCT, or URL mapping")
        source = Path(pdf_path)
        if not source.exists() or source.suffix.lower() != ".pdf":
            raise FileNotFoundError(source)
        kind, value = keyed
        document_id = f"{kind}:{value}"
        relative = Path("local_pdf") / source.name
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            target.write_bytes(source.read_bytes())
        record = {"document_id": document_id, "identifiers": {kind: value}, "candidate_ids": [],
                  "availability": "LOCAL_PDF_AVAILABLE", "content_type": "application/pdf",
                  "local_cache_path": relative.as_posix(), "source": "explicit-local-pdf",
                  "retrieved_at": None, "content_hash": file_hash(target),
                  "license_status": "USER_SUPPLIED", "resolution_attempts": [], "errors": []}
        return self._record(record)
    def resolve_identifier(self, item: dict[str, Any]) -> dict[str, Any]:
        keyed = _keyed_identifier(item)
        if not keyed:
            return {"document_id": "unrecognized:" + stable_hash(item)[:16], "identifiers": item,
                    "availability": "RESOLUTION_FAILED", "errors": [{"kind": "unrecognized_identifier"}]}
        kind, value = keyed
        if kind == "pmid":
            return self.resolve_pmid(value)
        if kind == "pmcid":
            return self.resolve_pmc(value)
        if kind == "nct":
            return self.resolve_nct(value)
        return {"document_id": f"{kind}:{value}", "identifiers": {kind: value},
                "availability": "DOI_IDENTIFIER_UNSUPPORTED" if kind == "doi" else "NO_DOCUMENT_IDENTIFIER",
                "source": "identifier-preserved-only",
                "identifier_status": item.get("identifier_status") or "UNSUPPORTED_DOCUMENT_IDENTIFIER",
                "original_identifier_type": item.get("original_identifier_type"),
                "resolution_attempts": [], "errors": [{"kind": "resolver_not_enabled", "identifier_type": kind}]}

    def resolve_live_identifier(self, item: dict[str, Any]) -> dict[str, Any]:
        """Resolve provenance with PMID?PMC preference and explicit abstract fallback."""
        keyed = _keyed_identifier(item)
        record = self.resolve_identifier(item)
        if keyed is None or keyed[0] != "pmid":
            return record
        requested_pmid = keyed[1]
        identifiers = record.get("identifiers") or {}
        pmcid_candidates = []
        if identifiers.get("pmcid"):
            pmcid_candidates.append(str(identifiers["pmcid"]))
        for candidate in record.get("pmcid_candidates") or []:
            if candidate and str(candidate) not in pmcid_candidates:
                pmcid_candidates.append(str(candidate))
        if not pmcid_candidates:
            return record
        rejected_pmcids = []
        pmc_attempts = []
        for pmcid in pmcid_candidates:
            pmc_record = self.resolve_pmc(pmcid)
            pmc_attempts.extend(pmc_record.get("resolution_attempts") or [])
            if pmc_record.get("availability") != "PMC_XML_AVAILABLE":
                continue
            resolved_pmid = self._pmc_article_pmid(pmc_record)
            if resolved_pmid != requested_pmid:
                rejected_pmcids.append({
                    "pmcid": pmcid,
                    "article_pmid": resolved_pmid or None,
                })
                continue
            pmc_record = dict(pmc_record)
            pmc_record.setdefault("identifiers", {})["pmid"] = requested_pmid
            pmc_record["requested_document_id"] = record.get("document_id")
            pmc_record["derived_pmcid"] = pmcid
            pmc_record["pmid_resolution"] = {
                "document_id": record.get("document_id"),
                "cache_hit": record.get("cache_hit", False),
                "availability": record.get("availability"),
                "requested_pmid": requested_pmid,
                "resolved_pmid": resolved_pmid,
            }
            return self._record(pmc_record) if not pmc_record.get("cache_hit") else pmc_record
        if rejected_pmcids:
            # A stale PMID cache entry can carry the wrong PMCID.  Ask the
            # configured NCBI resolver once for a fresh PMID record before
            # degrading to the already cached abstract.
            if self.network:
                refreshed = self.resolve_pmid(requested_pmid, force_refresh=True)
                refreshed_pmcid = (refreshed.get("identifiers") or {}).get("pmcid")
                if refreshed_pmcid and str(refreshed_pmcid) not in pmcid_candidates:
                    refreshed_pmc = self.resolve_pmc(str(refreshed_pmcid))
                    if refreshed_pmc.get("availability") == "PMC_XML_AVAILABLE":
                        refreshed_article_pmid = self._pmc_article_pmid(refreshed_pmc)
                        if refreshed_article_pmid == requested_pmid:
                            refreshed_pmc = dict(refreshed_pmc)
                            refreshed_pmc.setdefault("identifiers", {})["pmid"] = requested_pmid
                            refreshed_pmc["requested_document_id"] = record.get("document_id")
                            refreshed_pmc["derived_pmcid"] = str(refreshed_pmcid)
                            refreshed_pmc["pmid_resolution"] = {
                                "document_id": record.get("document_id"),
                                "cache_hit": refreshed.get("cache_hit", False),
                                "availability": refreshed.get("availability"),
                                "requested_pmid": requested_pmid,
                                "resolved_pmid": refreshed_article_pmid,
                                "recovery": "FORCED_NCBI_REFRESH",
                            }
                            return self._record(refreshed_pmc) if not refreshed_pmc.get("cache_hit") else refreshed_pmc
                        rejected_pmcids.append({
                            "pmcid": str(refreshed_pmcid),
                            "article_pmid": refreshed_article_pmid or None,
                        })
            # Never expose a rejected PMCID as the resolved document.  Retain
            # the PMID record so an authorized abstract can be used instead.
            record = dict(record)
            record["identifiers"] = {
                key: value for key, value in identifiers.items() if key != "pmcid"
            }
            record["degradation_reason"] = "PMC_IDENTITY_MISMATCH"
            record.setdefault("errors", []).append({
                "kind": "PMC_IDENTITY_MISMATCH",
                "requested_pmid": requested_pmid,
                "rejected_pmcids": rejected_pmcids,
            })
            record["rejected_pmcids"] = rejected_pmcids
            record["pmc_resolution"] = {
                "requested_pmid": requested_pmid,
                "rejected_pmcids": rejected_pmcids,
                "attempts": pmc_attempts,
            }
            if record.get("availability") != "ABSTRACT_AVAILABLE":
                record["availability"] = "DOCUMENT_UNAVAILABLE"
            return self._record(record) if not record.get("cache_hit") else record
        record["degradation_reason"] = "PMC_RESOLUTION_FAILED"
        record["pmc_resolution"] = {
            "requested_pmid": requested_pmid,
            "pmcid_candidates": pmcid_candidates,
            "attempts": pmc_attempts,
        }
        if record.get("availability") != "ABSTRACT_AVAILABLE":
            record = dict(record)
            record["availability"] = "DOCUMENT_UNAVAILABLE"
        return self._record(record) if not record.get("cache_hit") else record

    def _pmc_article_pmid(self, record: dict[str, Any]) -> str | None:
        """Read the PMID declared by a cached PMC XML payload.

        PMC identity is authoritative only when the payload itself declares a
        PMID.  Missing or malformed identity is therefore treated as a failed
        identity check by ``resolve_live_identifier``.
        """
        relative = record.get("local_cache_path")
        if not relative:
            return None
        path = self.root / relative
        if not path.is_file():
            return None
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            return None
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""
            if tag == "article-id" and element.attrib.get("pub-id-type", "").lower() == "pmid":
                # ElementTree has no parent pointers; iterate only descendants
                # of local-name article-meta nodes, never generic <pmid> or
                # reference nodes elsewhere in the document.
                for article_meta in root.iter():
                    meta_tag = article_meta.tag.rsplit("}", 1)[-1] if isinstance(article_meta.tag, str) else ""
                    if meta_tag != "article-meta":
                        continue
                    for declared in article_meta.iter():
                        declared_tag = declared.tag.rsplit("}", 1)[-1] if isinstance(declared.tag, str) else ""
                        if declared_tag == "article-id" and declared is element:
                            value = _norm(declared.text)
                            if value:
                                return value
        return None


    def source_units_for_record(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        units: list[dict[str, Any]] = []
        document_id = record["document_id"]
        relative = record.get("local_cache_path")
        if record.get("availability") == "ABSTRACT_AVAILABLE":
            if relative and (self.root / relative).is_file():
                payload = (self.root / relative).read_bytes()
                fields, _ = self._pubmed_xml_fields(payload)
                title, abstract = fields.get("title"), fields.get("abstract")
            else:
                title, abstract = record.get("title"), self.inline_abstract(record)
            units = [unit.to_dict() for unit in PubMedAbstractParser().parse(document_id, title, abstract)]
        elif relative and record.get("availability") == "PMC_XML_AVAILABLE":
            xml_text = (self.root / relative).read_text(encoding="utf-8", errors="replace")
            root = ET.fromstring(xml_text)
            for element in root.iter():
                if isinstance(element.tag, str) and "}" in element.tag:
                    element.tag = element.tag.split("}", 1)[1]
            article = root.find(".//article")
            article_text = ET.tostring(article, encoding="unicode") if article is not None else xml_text
            units = [unit.to_dict() for unit in JatsXmlParser().parse(document_id, article_text)]
        elif relative and record.get("availability") == "LOCAL_PDF_AVAILABLE":
            parsed, error = PdfDocumentParser().parse(document_id, self.root / relative)
            units = [unit.to_dict() for unit in parsed]
            if error:
                record.setdefault("errors", []).append({"kind": "pdf_parse", "error": error})
        elif record["document_id"].startswith("nct:") and relative:
            data = json.loads((self.root / relative).read_text(encoding="utf-8"))
            protocol = data.get("protocolSection", {})
            description = protocol.get("descriptionModule", {})
            identification = protocol.get("identificationModule", {})
            conditions = protocol.get("conditionsModule", {}).get("conditions", [])
            interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
            values = [("TRIAL_TITLE", identification.get("briefTitle")), ("BRIEF_SUMMARY", description.get("briefSummary")),
                      ("DETAILED_DESCRIPTION", description.get("detailedDescription"))]
            values += [("CONDITION", value) for value in conditions]
            values += [("INTERVENTION", item.get("name")) for item in interventions if item.get("name")]
            for unit_type, text in values:
                if text:
                    unit = SourceUnit.from_document_text(document_id, "ABSTRACT", str(text), locator_confidence="STRUCTURAL")
                    unit.unit_type = unit_type
                    units.append(unit.to_dict())
        return finalize_source_unit_occurrence_ids(document_id, units)


def attach_candidate_ids(records: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: dict[tuple[str, str], list[str]] = defaultdict(list)
    for candidate in candidates:
        for identifier in candidate.get("document_identifiers") or []:
            for expanded in expand_identifier(identifier):
                keyed = _keyed_identifier(expanded)
                if keyed:
                    mapping[keyed].append(candidate["candidate_id"])
    for record in records:
        candidate_ids: set[str] = set()
        for expanded in expand_identifier(record.get("identifiers", {})):
            keyed = _keyed_identifier(expanded)
            if keyed:
                candidate_ids.update(mapping.get(keyed, []))
        record["candidate_ids"] = sorted(candidate_ids)
    return records


def write_inventory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
