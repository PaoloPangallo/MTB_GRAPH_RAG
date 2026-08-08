"""Il bootstrap ricostruisce la cache che il runtime si aspetta, e nient'altro.

Due famiglie di verifiche, con presupposti diversi.

Le prime non richiedono la cache e non toccano la rete: riguardano il contratto
del bootstrap — quali percorsi dichiara di dover produrre, come classifica una
riga del manifest, e soprattutto che il closed set resti chiuso.

Le seconde girano solo quando la cache è stata ricostruita e verificano ciò che
nessun controllo di layout può dire: che le SourceUnit ri-parsate abbiano gli
stessi identificatori citati dai bundle congelati. È la proprietà da cui dipende
l'intera pipeline a valle, e l'unica il cui fallimento sarebbe silenzioso — una
cache valida, `document_cache_available` a `true`, e ogni bundle escluso con
``TEXT_NOT_AVAILABLE_IN_CACHE``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from backend.research_pipeline import data_access as da
from backend.research_pipeline.documents import cache_runtime

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load_bootstrap():
    """Carica lo script di bootstrap: sta in ``scripts/``, fuori dai package."""
    spec = importlib.util.spec_from_file_location(
        "bootstrap_research_document_cache", _SCRIPTS / "bootstrap_research_document_cache.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()

CACHE_AVAILABLE = cache_runtime.is_available()
CACHE_REASON = "cache documentale non ricostruita (scripts/bootstrap_research_document_cache.py)"

MANIFEST_ROWS = da.read_jsonl(da.document_manifest_path())


class BootstrapContractTest(TestCase):
    """Contratto del bootstrap. Nessuna cache, nessuna rete."""

    def test_document_id_prefix_selects_the_resolver(self) -> None:
        self.assertEqual(bootstrap.parse_document_id("pmid:19223544"), ("pmid", "19223544"))
        self.assertEqual(bootstrap.parse_document_id("pmcid:PMC248481"), ("pmcid", "PMC248481"))
        self.assertEqual(bootstrap.parse_document_id("nct:NCT02624973"), ("nct", "NCT02624973"))

    def test_a_pubmed_row_declares_both_abstract_and_metadata(self) -> None:
        """Contarne uno solo darebbe una cache diversa da quella misurata."""
        row = next(r for r in MANIFEST_ROWS if r["document_id"].startswith("pmid:"))
        self.assertEqual(len(bootstrap.expected_payloads(row)), 2)

    def test_rows_without_payload_are_classified_unavailable(self) -> None:
        for row in MANIFEST_ROWS:
            expected = (bootstrap.CLASS_EXPECTED_UNAVAILABLE if not row.get("local_cache_path")
                        else bootstrap.CLASS_EXPECTED_AVAILABLE)
            self.assertEqual(bootstrap.classify(row), expected, row["document_id"])

    def test_the_frozen_manifest_describes_the_documented_corpus(self) -> None:
        counts: dict[str, int] = {}
        for row in MANIFEST_ROWS:
            counts[bootstrap.classify(row)] = counts.get(bootstrap.classify(row), 0) + 1
        self.assertEqual(counts[bootstrap.CLASS_EXPECTED_AVAILABLE], 40)
        self.assertEqual(counts[bootstrap.CLASS_EXPECTED_UNAVAILABLE], 3)

    def test_expected_paths_stay_inside_the_directories_the_loader_requires(self) -> None:
        """Un percorso fuori dal layout non sarebbe risolvibile dal runtime."""
        allowed = cache_runtime._REQUIRED_SUBDIRECTORIES
        for row in MANIFEST_ROWS:
            for relative in bootstrap.expected_payloads(row):
                self.assertFalse(Path(relative).is_absolute(), relative)
                self.assertNotIn("..", Path(relative).parts, relative)
                self.assertIn(relative.split("/")[0], allowed, relative)

    def test_a_partial_document_is_not_considered_present(self) -> None:
        """Metà payload è un refetch, non un cache hit."""
        row = next(r for r in MANIFEST_ROWS if r["document_id"].startswith("pmid:"))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(bootstrap.payload_state(root, row), "MISSING")
            first = root / bootstrap.expected_payloads(row)[0]
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"payload")
            self.assertEqual(bootstrap.payload_state(root, row), "PARTIAL")

    def test_an_empty_file_does_not_count_as_a_payload(self) -> None:
        row = next(r for r in MANIFEST_ROWS if r["document_id"].startswith("nct:"))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / bootstrap.expected_payloads(row)[0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
            self.assertEqual(bootstrap.payload_state(root, row), "MISSING")

    def test_forgetting_an_entry_touches_only_the_bootstrap_manifest(self) -> None:
        """Il manifest congelato non è lo stato del bootstrap e non va scritto."""
        with TemporaryDirectory() as tmp:
            cache = cache_runtime.ReadOnlyDocumentCache(Path(tmp))
            cache.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            cache.manifest_path.write_text(
                json.dumps({"document_id": "pmid:1"}) + "\n"
                + json.dumps({"document_id": "pmid:2"}) + "\n", encoding="utf-8")
            bootstrap.forget_bootstrap_manifest_entry(cache, "pmid:1")
            kept = [json.loads(l)["document_id"]
                    for l in cache.manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(kept, ["pmid:2"])
            self.assertNotEqual(cache.manifest_path, da.document_manifest_path())


@skipUnless(CACHE_AVAILABLE, CACHE_REASON)
class RebuiltCacheLoadsSourceUnitsTest(TestCase):
    """Verifiche sulla cache ricostruita. Sola lettura, nessuna rete."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cache = cache_runtime.open_read_only()
        cls.index_ids = set(da.load_source_unit_index())
        cls.units: dict[str, dict] = {}
        for row in MANIFEST_ROWS:
            relative = row.get("local_cache_path")
            if relative and (cls.cache.root / relative).is_file():
                for unit in cls.cache.source_units_for_record(dict(row)):
                    cls.units[unit["source_unit_id"]] = unit

    def test_the_layout_satisfies_the_loader(self) -> None:
        available, reasons = cache_runtime.validate_cache()
        self.assertTrue(available, reasons)
        self.assertEqual(reasons, [])

    def test_every_expected_document_has_its_payload(self) -> None:
        missing = [row["document_id"] for row in MANIFEST_ROWS
                   if bootstrap.classify(row) == bootstrap.CLASS_EXPECTED_AVAILABLE
                   and bootstrap.payload_state(self.cache.root, row) != "PRESENT"]
        self.assertEqual(missing, [])

    def test_documents_declared_unavailable_stay_unresolvable(self) -> None:
        """Ricostruire la cache non deve promuovere un documento mai ottenuto."""
        for row in MANIFEST_ROWS:
            if bootstrap.classify(row) == bootstrap.CLASS_EXPECTED_UNAVAILABLE:
                self.assertIsNone(row.get("local_cache_path"), row["document_id"])

    def test_source_units_are_reconstructed_with_text(self) -> None:
        self.assertTrue(self.units)
        without_text = [uid for uid, unit in self.units.items()
                        if not (unit.get("text") or "").strip()]
        self.assertEqual(without_text, [])

    def test_reconstructed_identifiers_match_the_frozen_index(self) -> None:
        """La proprietà da cui dipende tutto il resto della pipeline."""
        rebuilt = set(self.units)
        self.assertEqual(rebuilt - self.index_ids, set(), "SourceUnit non presenti nell'indice")
        self.assertEqual(self.index_ids - rebuilt, set(), "SourceUnit dell'indice non ricostruite")

    def test_every_frozen_bundle_resolves_its_source_units(self) -> None:
        """Senza questo, ogni bundle uscirebbe con TEXT_NOT_AVAILABLE_IN_CACHE."""
        for bundle in da.read_jsonl(da.evidence_bundles_path()):
            requested = list(bundle.get("source_unit_ids") or [])
            resolved = [uid for uid in requested
                        if (self.units.get(uid, {}).get("text") or "").strip()]
            self.assertEqual(len(resolved), len(requested), bundle.get("bundle_id"))

    def test_reading_the_cache_never_reaches_the_network(self) -> None:
        with self.assertRaises(cache_runtime.CacheIsReadOnly):
            self.cache._request("https://eutils.ncbi.nlm.nih.gov/")
