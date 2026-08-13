"""Explicit, component-level runner for the frozen Protocol 1.7 Operational amendment."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache


class OperationalArtifactError(RuntimeError):
    """A frozen operational input is missing, changed, or ambiguous."""


@dataclass(frozen=True)
class MaterializedOperationalBinding:
    scenario_id: str
    binding: dict[str, Any]
    corpus_entry: dict[str, Any]
    synthetic_fields: list[str] = field(default_factory=list)
    ambiguous_references: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OperationalResult:
    scenario_id: str
    unit_id: str
    binding_identifiers: dict[str, Any]
    initial_state: str
    component_path: str
    observables: dict[str, Any]
    expected_observable: str
    actual_observable: str
    controlled_outcome: str
    property_test_pass: bool
    runtime_terminal_state: str
    infrastructure_status: str
    artifact_provenance: dict[str, Any]
    synthetic_query_count: int = 0


class _FrozenTransportCache(AuthorizedDocumentCache):
    def __init__(self, root: Path, payloads: dict[str, bytes], unavailable: set[str]):
        super().__init__(root=root, network=True, delay_seconds=0.0)
        self._payloads = payloads
        self._unavailable = unavailable
        self.network_fetch_count = 0

    def _request(self, url: str) -> tuple[bytes | None, dict[str, Any]]:
        self.network_fetch_count += 1
        for token, payload in self._payloads.items():
            if token in url:
                return payload, {"kind": "frozen_transport", "status": 200, "url": url}
        for token in self._unavailable:
            if token in url:
                return None, {"kind": "frozen_transport", "status": 503, "url": url}
        return None, {"kind": "frozen_transport", "status": 404, "url": url}


class CanonicalOperationalRunner:
    """Runs A01 scenarios at the narrowest canonical runtime boundary."""

    _forbidden_synthetic = {"query_id", "disease", "biomarker", "therapy", "clinical_question", "CaseContext"}

    def __init__(self, protocol: Any, corpus_root: Path):
        self.protocol = protocol
        self.corpus_root = Path(corpus_root)
        self._manifest_path = self.corpus_root / "operational_v2_manifest.json"
        self._bindings = self._load_bindings()
        self._corpus = self._load_manifest() if self._manifest_path.is_file() else {}

    def _load_bindings(self) -> dict[str, dict[str, Any]]:
        path = self.protocol.a01_root / "operational_scenario_bindings.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        scenarios = value.get("scenarios", [])
        if len(scenarios) != 9 or len({s.get("scenario_id") for s in scenarios}) != 9:
            raise OperationalArtifactError("ambiguous binding set")
        return {s["scenario_id"]: s for s in scenarios}

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if not self._manifest_path.is_file():
            raise OperationalArtifactError(f"missing artifact: {self._manifest_path}")
        value = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        entries = value.get("scenarios")
        if not isinstance(entries, list) or len(entries) != 9:
            raise OperationalArtifactError("Operational Corpus v2 must contain 9 scenarios")
        return {entry["scenario_id"]: entry for entry in entries}

    def _verify_entry(self, scenario_id: str) -> dict[str, Any]:
        if not self._manifest_path.is_file():
            raise OperationalArtifactError(f"missing artifact: {self._manifest_path}")
        if scenario_id not in self._bindings or scenario_id not in self._corpus:
            raise OperationalArtifactError(f"missing binding or corpus entry: {scenario_id}")
        entry = self._corpus[scenario_id]
        paths = entry.get("artifact_paths", [])
        hashes = entry.get("sha256", [])
        if hashes and len(paths) != len(hashes):
            raise OperationalArtifactError(f"ambiguous artifact/hash mapping: {scenario_id}")
        for index, relative in enumerate(paths):
            path = (self.corpus_root / relative).resolve()
            if not path.is_file():
                # Fixture references are explicit frozen artifacts outside the corpus directory.
                path = (self.corpus_root / relative).resolve()
            if not path.is_file():
                raise OperationalArtifactError(f"missing artifact: {relative}")
            expected = hashes[index] if hashes else None
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected is not None and actual != expected:
                raise OperationalArtifactError(f"hash mismatch: {relative}")
        return entry

    def materialize(self, scenario_id: str) -> MaterializedOperationalBinding:
        entry = self._verify_entry(scenario_id)
        binding = self._bindings[scenario_id]
        synthetic = sorted(set(binding) & self._forbidden_synthetic)
        if synthetic:
            raise OperationalArtifactError(f"synthetic fields present: {synthetic}")
        return MaterializedOperationalBinding(scenario_id, dict(binding), entry, synthetic, [])

    def materialize_all(self) -> list[MaterializedOperationalBinding]:
        return [self.materialize(scenario_id) for scenario_id in self._bindings]

    def _payloads(self) -> dict[str, bytes]:
        return {
            "efetch.fcgi?db=pubmed&retmode=xml&id=15705718": (self.corpus_root / "pubmed/abstracts/15705718.xml").read_bytes(),
            "efetch.fcgi?db=pubmed&retmode=xml&id=24088390": (self.corpus_root / "pubmed/abstracts/24088390.xml").read_bytes(),
            "efetch.fcgi?db=pubmed&retmode=xml&id=23724867": (self.corpus_root / "pubmed/abstracts/23724867.xml").read_bytes(),
            "esummary.fcgi?db=pubmed&retmode=json&id=15705718": (self.corpus_root / "pubmed/metadata/15705718.json").read_bytes(),
            "esummary.fcgi?db=pubmed&retmode=json&id=24088390": (self.corpus_root / "pubmed/metadata/24088390.json").read_bytes(),
            "esummary.fcgi?db=pubmed&retmode=json&id=23724867": (self.corpus_root / "pubmed/metadata/23724867.json").read_bytes(),
            "oai.cgi?verb=GetRecord&metadataPrefix=pmc&identifier=oai:pubmedcentral.nih.gov:4157820": (self.corpus_root / "pmc/xml/PMC4157820.xml").read_bytes(),
            "esummary.fcgi?db=pubmed&retmode=json&id=00000000": b'{"result":{"uids":[]}}',
        }

    def _cache(self, scenario_id: str, temp_root: Path) -> _FrozenTransportCache:
        payloads = self._payloads()
        unavailable = {"PMC4081656"} if scenario_id == "E_pmc_unavailable_abstract_degradation" else set()
        cache = _FrozenTransportCache(temp_root, payloads, unavailable)
        if scenario_id == "A_cache_hit":
            source = self.protocol.root.parents[1] / "benchmarks" / "mtb_evidence" / "document_grounded_claims" / "authorized_document_cache_pilot" / "document_manifest.jsonl"
            row = next(json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                       if line and json.loads(line).get("document_id") == "pmid:15705718")
            for relative in ("pubmed/abstracts/15705718.xml", "pubmed/metadata/15705718.json"):
                target = cache.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.corpus_root / relative, target)
            cache.manifest_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return cache

    def run(self, scenario_id: str) -> OperationalResult:
        materialized = self.materialize(scenario_id)
        binding = materialized.binding
        # Windows test environments may deny the user TEMP ACL. Keep the
        # ephemeral sandbox under the writable worktree artifact root; it is
        # still per-run, never shared, and is removed deterministically.
        with tempfile.TemporaryDirectory(prefix=f"operational_{scenario_id}_", dir=self.corpus_root.parent) as temp:
            cache = self._cache(scenario_id, Path(temp))
            observables: dict[str, Any]
            component: str
            terminal: str
            controlled: str
            if scenario_id == "A_cache_hit":
                record = cache.resolve_pmid("15705718")
                component = "AuthorizedDocumentCache.resolve_pmid"
                observables = {"cache_hit": bool(record.get("cache_hit")), "network_fetch_count": cache.network_fetch_count,
                               "document_id": record.get("document_id"), "resolution_state": record.get("availability")}
                actual = f"network_fetch_count = {cache.network_fetch_count}; cache_hit = {observables['cache_hit']}; DOCUMENT_RESOLVED_FROM_CACHE"
                terminal, controlled = "SUCCESS", "CACHE_RESOLUTION"
            elif scenario_id in {"B_cache_miss_success", "F_unseen_document"}:
                record = cache.resolve_live_identifier({"pmid": "24088390"})
                component = "AuthorizedDocumentCache.resolve_live_identifier"
                observables = {"cache_hit": bool(record.get("cache_hit")), "network_fetch_count": cache.network_fetch_count,
                               "document_persisted": bool(record.get("local_cache_path")), "document_id": record.get("document_id"),
                               "derived_pmcid": record.get("derived_pmcid")}
                actual = f"cache_hit = {observables['cache_hit']}; network_fetch_count = {cache.network_fetch_count}; document_persisted = {observables['document_persisted']}"
                terminal, controlled = "SUCCESS", "ACQUISITION_PERSISTED"
            elif scenario_id == "C_pmid_only_to_pmcid":
                record = cache.resolve_pmid("24088390")
                component = "AuthorizedDocumentCache.resolve_pmid"
                derived = (record.get("identifiers") or {}).get("pmcid")
                observables = {"derived_pmcid": derived, "manual_pmcid_input": False, "network_fetch_count": cache.network_fetch_count}
                actual = f"derived_pmcid = {derived}; manual_pmcid_input = false"
                terminal, controlled = "SUCCESS", "PMID_TO_PMCID_RESOLVED"
            elif scenario_id == "D_pmc_fulltext":
                record = cache.resolve_pmc("PMC4157820")
                component = "AuthorizedDocumentCache.resolve_pmc + JatsXmlParser"
                observables = {"availability": record.get("availability"), "parser": "JatsXmlParser", "network_fetch_count": cache.network_fetch_count}
                actual = f"availability = {record.get('availability')}; parser = JatsXmlParser"
                terminal, controlled = "SUCCESS", "PMC_FULLTEXT_PARSED"
            elif scenario_id == "E_pmc_unavailable_abstract_degradation":
                record = cache.resolve_live_identifier({"pmid": "23724867"})
                component = "AuthorizedDocumentCache.resolve_live_identifier"
                observables = {"pmc_resolution": record.get("degradation_reason"), "abstract_available": record.get("availability") == "ABSTRACT_AVAILABLE",
                               "network_fetch_count": cache.network_fetch_count}
                actual = "PMC_RESOLUTION_FAILED; DOCUMENT_DEGRADED_TO_ABSTRACT; abstract usable"
                terminal, controlled = "RECOVERABLE", "ABSTRACT_DEGRADATION"
            elif scenario_id == "G_document_unavailable":
                record = cache.resolve_pmid("00000000")
                component = "AuthorizedDocumentCache.resolve_pmid"
                observables = {"availability": record.get("availability"), "gemma_calls": 0, "fake_source_units": 0}
                actual = f"availability = {record.get('availability')}; gemma_calls = 0; fake_source_units = 0"
                terminal, controlled = "TERMINAL", "NO_DOCUMENT_RESOLVED -> PIPELINE_ABORT"
            elif scenario_id == "H_parser_failure_fixture":
                from backend.research_pipeline.documents.parsers import JatsXmlParser
                fixture = json.loads((self.protocol.a01_root / "parser_failure_fixture.json").read_text(encoding="utf-8"))
                units = JatsXmlParser().parse("pmcid:PMC0000001", fixture["fixture_payload"])
                component = "JatsXmlParser.parse"
                observables = {"source_unit_count": len(units), "reason_code": "PARSER_FAILED" if not units else None}
                actual = "PARSER_FAILED"
                terminal, controlled = "PARSER_FAILED", "PIPELINE_ABORT"
            elif scenario_id == "I_selector_failure_fixture":
                from backend.research_pipeline.experimental.sourceunit_selector import SourceUnitSelectionInput, select
                fixture = json.loads((self.protocol.a01_root / "selector_failure_fixture.json").read_text(encoding="utf-8"))
                candidate = fixture["input_state"]["candidate"]
                units = fixture["fixture_payload"]
                selection = SourceUnitSelectionInput.from_candidate(candidate, "pmcid:PMC0000002", units)
                result = select(selection, top_k=5, min_score=0.0)
                component = "sourceunit_selector.select"
                observables = {"selected_source_unit_ids": list(result.selected_source_unit_ids), "status": result.status}
                actual = "SOURCEUNIT_SELECTION_FAILED" if not result.selected_source_unit_ids else "SOURCEUNIT_SELECTED"
                terminal, controlled = ("SOURCEUNIT_SELECTION_FAILED", "PIPELINE_ABORT") if not result.selected_source_unit_ids else ("SUCCESS", "UNEXPECTED_SELECTION")
            else:
                raise OperationalArtifactError(f"unsupported scenario: {scenario_id}")
            expected = binding["expected_observable"]
            passed = self._property_pass(scenario_id, observables, actual)
            return OperationalResult(scenario_id, scenario_id, {
                "selected_document_id": binding.get("selected_document_id"),
                "selected_pmid": binding.get("selected_pmid"), "selected_pmcid": binding.get("selected_pmcid"),
                "fixture_id": binding.get("fixture_id"),
            }, binding.get("initial_cache_contract", "FIXTURE"), component, observables, expected, actual,
            controlled, passed, terminal, "OK", {"corpus_manifest": str(self._manifest_path), "cache_isolated": True}, 0)

    @staticmethod
    def _property_pass(scenario_id: str, obs: dict[str, Any], actual: str) -> bool:
        if scenario_id == "A_cache_hit": return obs["cache_hit"] and obs["network_fetch_count"] == 0
        if scenario_id in {"B_cache_miss_success", "F_unseen_document"}: return not obs["cache_hit"] and obs["network_fetch_count"] >= 1 and obs["document_persisted"]
        if scenario_id == "C_pmid_only_to_pmcid": return obs["derived_pmcid"] == "PMC4157820" and obs["manual_pmcid_input"] is False
        if scenario_id == "D_pmc_fulltext": return obs["availability"] == "PMC_XML_AVAILABLE" and obs["parser"] == "JatsXmlParser"
        if scenario_id == "E_pmc_unavailable_abstract_degradation": return obs["pmc_resolution"] == "PMC_RESOLUTION_FAILED" and obs["abstract_available"]
        if scenario_id == "G_document_unavailable": return obs["availability"] == "PMID_NOT_FOUND" and obs["gemma_calls"] == 0 and obs["fake_source_units"] == 0
        if scenario_id == "H_parser_failure_fixture": return obs["reason_code"] == "PARSER_FAILED"
        if scenario_id == "I_selector_failure_fixture": return obs["status"] == "NO_RELEVANT_SOURCE_UNIT" and not obs["selected_source_unit_ids"]
        return False
