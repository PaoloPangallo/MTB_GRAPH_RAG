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
from pathlib import Path
from typing import Any

from .parsers import JatsXmlParser, PdfDocumentParser, PubMedAbstractParser
from .models import SourceUnit

PMID_RE = re.compile(r"^\d+$")
NCT_RE = re.compile(r"^NCT\d{8}$", re.I)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
URL_RE = re.compile(r"^https?://", re.I)


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        return [{kind: part, **({"scope": item["scope"]} if item.get("scope") else {})} for part in parts]
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
    resolver_version = "authorized-cache/1.0"

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

    @staticmethod
    def _pubmed_xml_fields(payload: bytes) -> tuple[dict[str, Any], str | None]:
        root = ET.fromstring(payload)
        article = root.find(".//PubmedArticle")
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
        for node in article.findall(".//ArticleId"):
            if node.attrib.get("IdType", "").lower() == "pmc":
                pmcid = (node.text or "").strip().upper()
        doi = None
        for node in article.findall(".//ArticleId"):
            if node.attrib.get("IdType", "").lower() == "doi":
                doi = (node.text or "").strip().lower()
        publication_types = ["".join(n.itertext()).strip() for n in article.findall(".//PublicationType")]
        return {"title": title, "abstract": abstract, "abstract_sections": sections,
                "pmcid": pmcid, "doi": doi, "publication_types": publication_types}, pmcid

    def resolve_pmid(self, pmid: str) -> dict[str, Any]:
        pmid = _norm(pmid)
        document_id = f"pmid:{pmid}"
        cached = self._cached_manifest(document_id)
        if cached:
            cached = dict(cached)
            cached["cache_hit"] = True
            return cached
        record: dict[str, Any] = {"document_id": document_id, "identifiers": {"pmid": pmid},
                                  "candidate_ids": [], "availability": "RESOLUTION_FAILED",
                                  "content_type": None, "local_cache_path": None, "source": "NCBI E-utilities",
                                  "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                  "content_hash": None, "license_status": "PUBLIC_METADATA_ABSTRACT",
                                  "resolution_attempts": [], "errors": []}
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
                    fields, pmcid = self._pubmed_xml_fields(abstract_payload)
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
        if cached:
            cached["cache_hit"] = True
            return cached
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
                "availability": "NO_DOCUMENT_IDENTIFIER", "source": "identifier-preserved-only",
                "resolution_attempts": [], "errors": [{"kind": "resolver_not_enabled", "identifier_type": kind}]}

    def source_units_for_record(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        units: list[dict[str, Any]] = []
        document_id = record["document_id"]
        relative = record.get("local_cache_path")
        if relative and record.get("availability") == "ABSTRACT_AVAILABLE":
            payload = (self.root / relative).read_bytes()
            fields, _ = self._pubmed_xml_fields(payload)
            units = [unit.to_dict() for unit in PubMedAbstractParser().parse(document_id, fields.get("title"), fields.get("abstract"))]
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
        return units


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
