import hashlib
import json

import pytest

from backend.research_pipeline.terminology.build import import_snapshot, checked_bytes
from backend.research_pipeline.terminology.registry import Registry


def test_snapshot_scopes_obsolete_and_mapping_semantics(tmp_path):
    data = b'''format-version: 1.2
[Term]
id: DOID:1
name: carcinoma
synonym: "exact carcinoma" EXACT []
synonym: "neoplasm" BROAD []
xref: NCIT:C1
is_a: DOID:2 ! disease
[Term]
id: DOID:3
name: old carcinoma
is_obsolete: true
replaced_by: DOID:1
'''
    (tmp_path / "source.obo").write_bytes(data)
    manifest = {"schema_version": "terminology-source/1.0", "file": "source.obo",
                "sha256": hashlib.sha256(data).hexdigest(), "version": "fixture/1",
                "format": "OBO", "domain": "DISEASE", "namespace": "DOID"}
    path = tmp_path / "source.json"
    path.write_text(json.dumps(manifest))
    terms, mappings = import_snapshot(path)
    registry = Registry(terms, "test", mappings)
    assert registry.resolve("DISEASE", "exact carcinoma").concept_ids == ("DOID:1",)
    assert registry.resolve("DISEASE", "neoplasm").status == "UNMAPPED"
    assert registry.resolve("DISEASE", "old carcinoma").status == "UNMAPPED"
    assert registry.resolve("DISEASE", "NCIT:C1").status == "UNMAPPED"
    assert {m["predicate"] for m in mappings} == {"XREF_UNSPECIFIED", "IS_A", "REPLACED_BY", "OBSOLETE"}


def test_hash_checked_before_parse(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="hash"):
        checked_bytes(path, "0" * 64)
