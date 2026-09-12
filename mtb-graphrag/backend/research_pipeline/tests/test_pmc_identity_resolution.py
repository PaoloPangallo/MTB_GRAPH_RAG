from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache


def _pmc_xml(pmid: str) -> str:
    return f"<article><front><article-meta><article-id pub-id-type=\"pmid\">{pmid}</article-id></article-meta></front></article>"


def _pubmed_xml(pmid: str) -> str:
    return f"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article><ArticleTitle>Cached abstract</ArticleTitle><Abstract><AbstractText>Relevant abstract.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"


class PmcIdentityResolutionTest(TestCase):
    def _cache(self, root: Path, *, requested: str, pmcid: str, pmc_pmid: str,
               abstract: bool = False, extra: dict | None = None) -> AuthorizedDocumentCache:
        cache = AuthorizedDocumentCache(root=root, network=False)
        pmc_rel = f"pmc/xml/{pmcid}.xml"
        (root / pmc_rel).parent.mkdir(parents=True, exist_ok=True)
        (root / pmc_rel).write_text(_pmc_xml(pmc_pmid), encoding="utf-8")
        pmid_rel = f"pubmed/abstracts/{requested}.xml"
        if abstract:
            (root / pmid_rel).parent.mkdir(parents=True, exist_ok=True)
            (root / pmid_rel).write_text(_pubmed_xml(requested), encoding="utf-8")
        rows = [{
            "document_id": f"pmid:{requested}",
            "identifiers": {"pmid": requested, "pmcid": pmcid},
            "availability": "ABSTRACT_AVAILABLE" if abstract else "METADATA_ONLY",
            "local_cache_path": pmid_rel if abstract else None,
            "cache_hit": True,
            **(extra or {}),
        }, {
            "document_id": f"pmcid:{pmcid}",
            "identifiers": {"pmcid": pmcid},
            "availability": "PMC_XML_AVAILABLE",
            "local_cache_path": pmc_rel,
            "cache_hit": True,
        }]
        (root / "manifests").mkdir(parents=True, exist_ok=True)
        (root / "manifests/documents.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        return cache

    def test_matching_pmc_is_accepted(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._cache(Path(tmp), requested="100", pmcid="PMC100", pmc_pmid="100").resolve_live_identifier({"pmid": "100"})
            self.assertEqual("pmcid:PMC100", result["document_id"])
            self.assertEqual("PMC100", result["derived_pmcid"])

    def test_mismatching_pmc_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._cache(Path(tmp), requested="100", pmcid="PMC200", pmc_pmid="200").resolve_live_identifier({"pmid": "100"})
            self.assertEqual("DOCUMENT_UNAVAILABLE", result["availability"])
            self.assertEqual("PMC_IDENTITY_MISMATCH", result["degradation_reason"])
            self.assertNotIn("pmcid", result["identifiers"])

    def test_mismatching_pmc_falls_back_to_valid_abstract(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._cache(Path(tmp), requested="100", pmcid="PMC200", pmc_pmid="200", abstract=True).resolve_live_identifier({"pmid": "100"})
            self.assertEqual("pmid:100", result["document_id"])
            self.assertEqual("ABSTRACT_AVAILABLE", result["availability"])
            self.assertEqual("PMC_IDENTITY_MISMATCH", result["degradation_reason"])

    def test_correct_candidate_pmc_is_selected_after_wrong_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = self._cache(root, requested="100", pmcid="PMC200", pmc_pmid="200", extra={"pmcid_candidates": ["PMC300"]})
            (root / "pmc/xml/PMC300.xml").write_text(_pmc_xml("100"), encoding="utf-8")
            with (root / "manifests/documents.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"document_id": "pmcid:PMC300", "identifiers": {"pmcid": "PMC300"}, "availability": "PMC_XML_AVAILABLE", "local_cache_path": "pmc/xml/PMC300.xml", "cache_hit": True}) + "\n")
            result = cache.resolve_live_identifier({"pmid": "100"})
            self.assertEqual("pmcid:PMC300", result["document_id"])

    def test_force_refresh_recovers_authoritative_pmc(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = self._cache(root, requested="100", pmcid="PMC200", pmc_pmid="200")
            (root / "pmc/xml/PMC300.xml").write_text(_pmc_xml("100"), encoding="utf-8")
            with (root / "manifests/documents.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"document_id": "pmcid:PMC300", "identifiers": {"pmcid": "PMC300"}, "availability": "PMC_XML_AVAILABLE", "local_cache_path": "pmc/xml/PMC300.xml", "cache_hit": True}) + "\n")
            original = cache.resolve_pmid
            def refreshed(pmid: str, *, force_refresh: bool = False):
                if force_refresh:
                    return {"document_id": "pmid:100", "identifiers": {"pmid": "100", "pmcid": "PMC300"}, "availability": "METADATA_ONLY", "cache_hit": True}
                return original(pmid)
            cache.resolve_pmid = refreshed  # type: ignore[method-assign]
            cache.network = True
            result = cache.resolve_live_identifier({"pmid": "100"})
            self.assertEqual("pmcid:PMC300", result["document_id"])

    def test_missing_pmc_identity_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = self._cache(root, requested="100", pmcid="PMC200", pmc_pmid="")
            result = cache.resolve_live_identifier({"pmid": "100"})
            self.assertEqual("DOCUMENT_UNAVAILABLE", result["availability"])
            self.assertEqual("PMC_IDENTITY_MISMATCH", result["degradation_reason"])

    def test_mismatching_pmc_without_abstract_is_unavailable(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._cache(Path(tmp), requested="100", pmcid="PMC200", pmc_pmid="200").resolve_live_identifier({"pmid": "100"})
            self.assertFalse((result.get("local_cache_path") or "").startswith("pmc/"))
            self.assertEqual("DOCUMENT_UNAVAILABLE", result["availability"])

    def test_offline_resolver_uses_configured_authoritative_cache_when_primary_root_misses(self) -> None:
        with TemporaryDirectory() as primary_tmp, TemporaryDirectory() as authoritative_tmp:
            primary = Path(primary_tmp)
            authoritative = Path(authoritative_tmp)
            pmcid = "PMC300"
            relative = f"pmc/xml/{pmcid}.xml"
            payload = _pmc_xml("100").encode("utf-8")
            (authoritative / relative).parent.mkdir(parents=True, exist_ok=True)
            (authoritative / relative).write_bytes(payload)
            row = {
                "document_id": f"pmcid:{pmcid}",
                "identifiers": {"pmcid": pmcid},
                "availability": "PMC_XML_AVAILABLE",
                "local_cache_path": relative,
                "content_hash": hashlib.sha256(payload).hexdigest(),
            }
            (authoritative / "manifests").mkdir(parents=True, exist_ok=True)
            (authoritative / "manifests/documents.jsonl").write_text(
                json.dumps(row) + "\n", encoding="utf-8"
            )
            cache = self._cache(primary, requested="100", pmcid=pmcid, pmc_pmid="100")
            primary_manifest = primary / "manifests/documents.jsonl"
            primary_manifest.write_text(
                json.dumps({"document_id": "pmid:100", "identifiers": {"pmid": "100", "pmcid": pmcid},
                            "availability": "METADATA_ONLY"}) + "\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"RESEARCH_DOCUMENT_AUTHORITATIVE_CACHE_ROOT": str(authoritative)}):
                result = cache.resolve_live_identifier({"pmid": "100"})
            self.assertEqual("pmcid:PMC300", result["document_id"])
            self.assertEqual("PMC_XML_AVAILABLE", result["availability"])
            self.assertTrue(Path(result["local_cache_path"]).is_file())
            self.assertEqual("100", cache._pmc_article_pmid(result))

    def test_authoritative_cache_index_without_payload_fails_closed(self) -> None:
        with TemporaryDirectory() as primary_tmp, TemporaryDirectory() as authoritative_tmp:
            primary = Path(primary_tmp)
            authoritative = Path(authoritative_tmp)
            cache = self._cache(primary, requested="100", pmcid="PMC300", pmc_pmid="200")
            (primary / "manifests/documents.jsonl").write_text(
                json.dumps({"document_id": "pmid:100", "identifiers": {"pmid": "100", "pmcid": "PMC300"},
                            "availability": "METADATA_ONLY"}) + "\n",
                encoding="utf-8",
            )
            (authoritative / "manifests").mkdir(parents=True, exist_ok=True)
            (authoritative / "manifests/documents.jsonl").write_text(json.dumps({
                "document_id": "pmcid:PMC300", "identifiers": {"pmcid": "PMC300"},
                "availability": "PMC_XML_AVAILABLE", "local_cache_path": "pmc/xml/PMC300.xml",
            }) + "\n", encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_DOCUMENT_AUTHORITATIVE_CACHE_ROOT": str(authoritative)}):
                result = cache.resolve_live_identifier({"pmid": "100"})
            self.assertEqual("DOCUMENT_UNAVAILABLE", result["availability"])
            self.assertIsNone(result.get("local_cache_path"))

    def test_authoritative_cache_requires_content_hash(self) -> None:
        with TemporaryDirectory() as primary_tmp, TemporaryDirectory() as authoritative_tmp:
            primary = Path(primary_tmp)
            authoritative = Path(authoritative_tmp)
            cache = self._cache(primary, requested="100", pmcid="PMC300", pmc_pmid="200")
            relative = Path("pmc/xml/PMC300.xml")
            (authoritative / relative).parent.mkdir(parents=True, exist_ok=True)
            (authoritative / relative).write_text(_pmc_xml("100"), encoding="utf-8")
            (authoritative / "manifests").mkdir(parents=True, exist_ok=True)
            (authoritative / "manifests/documents.jsonl").write_text(json.dumps({
                "document_id": "pmcid:PMC300", "identifiers": {"pmcid": "PMC300"},
                "availability": "PMC_XML_AVAILABLE", "local_cache_path": relative.as_posix(),
            }) + "\n", encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_DOCUMENT_AUTHORITATIVE_CACHE_ROOT": str(authoritative)}):
                result = cache.resolve_live_identifier({"pmid": "100"})
            self.assertEqual("DOCUMENT_UNAVAILABLE", result["availability"])
