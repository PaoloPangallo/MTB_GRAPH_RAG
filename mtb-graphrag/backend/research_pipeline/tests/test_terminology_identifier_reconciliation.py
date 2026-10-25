from backend.research_pipeline.terminology.build import reconcile_source_identifiers
from backend.research_pipeline.terminology.models import SourceRef, Term


def term(cid, label, asset="csv", scope="PREFERRED"):
    return Term("DISEASE", cid, label, scope, SourceRef(asset, "fixture", "hash", cid))


def test_reconcile_only_unique_authority_with_exact_label_and_keep_provenance():
    original = term("DOID:123", "Example disease")
    authority = term("DOID:0000123", "example disease", "obo")
    terms, mappings = reconcile_source_identifiers([original], [authority])
    assert terms[0].concept_id == authority.concept_id
    assert terms[0].source == original.source
    assert mappings[0]["subject"] == original.concept_id
    assert mappings[0]["object"] == authority.concept_id
    assert mappings[0]["authority_source"] == authority.source.__dict__


def test_no_repair_without_exact_identity_scope_label():
    original = term("DOID:123", "different disease")
    authority = term("DOID:0000123", "example disease", "obo")
    assert reconcile_source_identifiers([original], [authority]) == ([original], [])
    broad = term("DOID:0000123", "different disease", "obo", "BROAD")
    assert reconcile_source_identifiers([original], [broad]) == ([original], [])


def test_numeric_collision_is_never_merged_even_when_labels_match():
    original = term("DOID:123", "example disease")
    authorities = [term("DOID:00123", "example disease", "obo"),
                   term("DOID:000123", "example disease", "obo")]
    assert reconcile_source_identifiers([original], authorities) == ([original], [])


def test_existing_authoritative_ids_and_other_namespaces_are_unchanged():
    original = term("DOID:123", "example disease")
    authorities = [term("DOID:123", "other disease", "obo"),
                   term("DOID:00123", "example disease", "obo")]
    assert reconcile_source_identifiers([original], authorities) == ([original], [])
    other = term("NCIT:123", "example disease")
    assert reconcile_source_identifiers([other], authorities) == ([other], [])


def test_authority_alternate_identifier_numeric_collision_blocks_repair():
    original = term("DOID:123", "example disease")
    authority = term("DOID:00123", "example disease", "obo")
    alternate = term("DOID:999", "DOID:000123", "obo", "EXACT")
    assert reconcile_source_identifiers([original], [authority, alternate]) == ([original], [])


def test_retired_identifier_numeric_collision_blocks_repair():
    original = term("DOID:123", "example disease")
    authority = term("DOID:00123", "example disease", "obo")
    retired = [{"subject": "DOID:000123", "predicate": "OBSOLETE"}]
    assert reconcile_source_identifiers([original], [authority], retired) == ([original], [])
