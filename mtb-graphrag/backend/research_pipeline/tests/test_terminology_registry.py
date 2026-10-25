import json
import hashlib

import pytest

from backend.research_pipeline.terminology.models import SourceRef, Term
from backend.research_pipeline.terminology.registry import Registry
from backend.research_pipeline.terminology.loader import load_registry, TerminologyAssetError


def term(cid, label, domain="GENE", scope="EXACT", gene_id=None):
    return Term(domain, cid, label, scope, SourceRef("fixture", "1", "a" * 64, "row:1"), gene_id)


def test_collision_is_order_independent_and_never_overwritten():
    terms = [term("NCBIGene:1", "shared"), term("NCBIGene:2", "shared")]
    for items in [terms, list(reversed(terms))]:
        registry = Registry(items, "fixture/1")
        result = registry.resolve("GENE", "shared")
        assert result.status == "AMBIGUOUS"
        assert result.concept_ids == ("NCBIGene:1", "NCBIGene:2")
        assert registry.resolve("GENE", "absent").status == "UNMAPPED"


def test_direct_id_precedence_and_namespace_isolation():
    registry = Registry([term("NCBIGene:1", "same"), term("DOID:1", "same", "DISEASE")], "1")
    assert registry.resolve("GENE", "NCBIGene:1").concept_ids == ("NCBIGene:1",)
    assert registry.resolve("GENE", "DOID:1").status == "UNMAPPED"


def test_broad_related_synonyms_are_not_identity_aliases():
    registry = Registry([term("DOID:1", "specific", "DISEASE", "PREFERRED"),
                         term("DOID:1", "broad", "DISEASE", "BROAD"),
                         term("DOID:1", "related", "DISEASE", "RELATED")], "1")
    assert registry.resolve("DISEASE", "specific").status == "RESOLVED"
    assert registry.resolve("DISEASE", "broad").status == "UNMAPPED"
    assert registry.resolve("DISEASE", "related").status == "UNMAPPED"


def test_alias_collision_with_preferred_symbol_remains_visible():
    registry = Registry([term("NCBIGene:1", "X", scope="PREFERRED"),
                         term("NCBIGene:2", "X")], "1")
    assert registry.resolve("GENE", "X").status == "AMBIGUOUS"


def test_typed_variant_alias_keeps_gene_context():
    registry = Registry([term("CIViCVariant:1", "G12D", "VARIANT", gene_id="NCBIGene:1"),
                         term("CIViCVariant:2", "G12D", "VARIANT", gene_id="NCBIGene:2")], "1")
    assert registry.resolve("VARIANT", "G12D").status == "AMBIGUOUS"
    assert registry.resolve("VARIANT", "p.Gly12Asp", gene_id="NCBIGene:1").concept_ids == ("CIViCVariant:1",)


def test_validated_asset_loading_and_hash_rejection(tmp_path):
    registry = Registry([term("NCBIGene:1", "X")], "fixture/1")
    payload = json.dumps(registry.to_dict()).encode()
    (tmp_path / "registry.json").write_bytes(payload)
    manifest = {"schema_version": "terminology-manifest/1.0", "registry_version": "fixture/1",
                "registry_file": "registry.json", "registry_sha256": hashlib.sha256(payload).hexdigest()}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert load_registry(path).resolve("GENE", "X").status == "RESOLVED"
    (tmp_path / "registry.json").write_text("{}")
    with pytest.raises(TerminologyAssetError, match="hash"):
        load_registry(path)


@pytest.mark.parametrize("field,value", [("schema_version", "future/99"), ("registry_file", "../outside.json")])
def test_invalid_manifest_is_rejected(tmp_path, field, value):
    manifest = {"schema_version": "terminology-manifest/1.0", "registry_file": "registry.json"}
    manifest[field] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(TerminologyAssetError):
        load_registry(path)
