import json
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.research_pipeline.documents.cache_runtime import ReadOnlyDocumentCache
from backend.research_pipeline.documents.parsers import JatsXmlParser
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_ROOT = PROJECT_ROOT / "data_cache" / "document_grounding"


def _manifest_record(document_id):
    manifest = CACHE_ROOT / "manifests" / "documents.jsonl"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("document_id") == document_id:
            return record
    raise AssertionError(f"missing cache record {document_id}")


def _resolved_pmid(pmcid):
    manifest = CACHE_ROOT / "manifests" / "runtime_v2_pmid_resolution.jsonl"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("pmcid") == pmcid:
            return record.get("pmid")
    return None


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _normalized_text(node):
    return " ".join("".join(node.itertext()).split())


def _document_body_paragraphs(record):
    payload = CACHE_ROOT / record["local_cache_path"]
    root = ET.parse(payload).getroot()
    body = next(node for node in root.iter() if _local_name(node.tag) == "body")
    paragraphs = []

    def walk(node, in_table_or_figure=False):
        tag = _local_name(node.tag)
        in_table_or_figure = in_table_or_figure or tag in {"table-wrap", "fig"}
        if tag == "p" and not in_table_or_figure:
            text = _normalized_text(node)
            if text:
                paragraphs.append(text)
            return
        for child in node:
            walk(child, in_table_or_figure)

    walk(body)
    return paragraphs


def test_real_jats_abstract_is_emitted_without_copying_it_as_a_paragraph():
    record = _manifest_record("pmcid:PMC3288377")
    units = ReadOnlyDocumentCache(CACHE_ROOT).source_units_for_record(record)
    xml = ET.parse(CACHE_ROOT / record["local_cache_path"]).getroot()
    abstract = next(node for node in xml.iter() if _local_name(node.tag) == "abstract")
    abstract_text = _normalized_text(abstract)

    assert abstract_text
    assert any(unit["text"] == abstract_text for unit in units)
    assert sum(unit["unit_type"] == "ABSTRACT" and unit["text"] == abstract_text for unit in units) == 1
    assert not any(
        unit["unit_type"] == "FULLTEXT_PARAGRAPH" and unit["text"] == abstract_text
        for unit in units
    )


def test_real_jats_unsectioned_body_paragraphs_are_kept_in_document_order():
    record = _manifest_record("pmcid:PMC3288377")
    expected = _document_body_paragraphs(record)
    units = ReadOnlyDocumentCache(CACHE_ROOT).source_units_for_record(record)
    actual = [
        unit["text"]
        for unit in units
        if unit["unit_type"] == "FULLTEXT_PARAGRAPH"
    ]

    assert expected
    assert actual == expected
    assert len(actual) == len(expected)


def test_real_nested_jats_sections_keep_section_and_subsection_provenance():
    record = _manifest_record("pmcid:PMC4067722")
    cache = ReadOnlyDocumentCache(CACHE_ROOT)
    units = cache.source_units_for_record(record)
    repeated_parse = cache.source_units_for_record(record)
    context = [unit for unit in units if unit.get("section") == "Context"]

    assert context
    assert any("Such tumors frequently harbor BRAF V600E" in unit["text"] for unit in context)
    assert all(unit["document_id"] == record["document_id"] for unit in context)
    assert all(unit.get("parser") == "JatsXmlParser" for unit in context)
    assert _resolved_pmid("PMC4067722") == "24987354"
    assert len({unit["source_unit_id"] for unit in context}) == len(context)
    assert [(u["source_unit_id"], u.get("content_hash"), u.get("paragraph_index")) for u in units] == [
        (u["source_unit_id"], u.get("content_hash"), u.get("paragraph_index")) for u in repeated_parse
    ]


def test_new_jats_sentence_remains_authorized_for_reader_quote_validation():
    record = _manifest_record("pmcid:PMC4067722")
    document_id = record["document_id"]
    units = ReadOnlyDocumentCache(CACHE_ROOT).source_units_for_record(record)
    quote = "Such tumors frequently harbor BRAF V600E, and this alteration may predict responsiveness to vemurafenib treatment."
    abstract_unit = next(unit for unit in units if unit["unit_type"] == "ABSTRACT" and quote in unit["text"])
    by_id = {unit["source_unit_id"]: unit for unit in units}

    result = validate_enrichment_v3(
        "V3_TRANSPORT_VALID",
        {"decision": "QUOTE", "source_unit_id": abstract_unit["source_unit_id"], "quote": quote},
        candidate={},
        # The Reader receives an explicit selected-unit allowlist, not every
        # unit from the resolved document.
        paper_bundle={"document_id": document_id, "source_unit_ids": [abstract_unit["source_unit_id"]]},
        source_units_by_id=by_id,
    )

    assert result["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    assert by_id[abstract_unit["source_unit_id"]]["document_id"] == document_id

    unselected_unit = next(unit for unit in units if unit["source_unit_id"] != abstract_unit["source_unit_id"])
    rejected = validate_enrichment_v3(
        "V3_TRANSPORT_VALID",
        {"decision": "QUOTE", "source_unit_id": unselected_unit["source_unit_id"],
         "quote": unselected_unit["text"][:40]},
        candidate={},
        paper_bundle={"document_id": document_id, "source_unit_ids": [abstract_unit["source_unit_id"]]},
        source_units_by_id=by_id,
    )
    assert rejected["outcome"] == "QUOTE_INVALID"
    assert rejected["reason_codes"] == ["SOURCE_UNIT_NOT_IN_SELECTED_DOCUMENT"]


def test_foreign_document_source_unit_cannot_be_used_even_if_present_in_lookup():
    allowed = {
        "source_unit_id": "allowed-unit",
        "document_id": "pmcid:PMC-allowed",
        "text": "The paper reports a response.",
    }
    foreign = {
        "source_unit_id": "foreign-unit",
        "document_id": "pmcid:PMC-foreign",
        "text": "The paper reports a response.",
    }
    result = validate_enrichment_v3(
        "V3_TRANSPORT_VALID",
        {"decision": "QUOTE", "source_unit_id": "foreign-unit", "quote": foreign["text"]},
        candidate={},
        paper_bundle={"document_id": "pmcid:PMC-allowed", "source_unit_ids": ["allowed-unit"]},
        source_units_by_id={"allowed-unit": allowed, "foreign-unit": foreign},
    )
    assert result["outcome"] == "QUOTE_INVALID"
    assert result["reason_codes"] == ["SOURCE_UNIT_NOT_IN_SELECTED_DOCUMENT"]


def test_namespaced_jats_and_inline_markup_keep_readable_text_and_section():
    xml = """<article xmlns="urn:jats:test"><front><article-meta>
      <title-group><article-title>Paper title</article-title></title-group>
      <abstract><p>EGFR <italic>L858R</italic> predicts response.</p></abstract>
    </article-meta></front><body><sec><title>Results</title><sec><title>Patients</title>
      <p>Patients with <italic>EGFR</italic> L858R responded.</p>
    </sec></sec></body></article>"""
    units = [unit.to_dict() for unit in JatsXmlParser().parse("pmcid:PMC-fixture", xml)]

    abstract = next(unit for unit in units if unit["unit_type"] == "ABSTRACT")
    paragraph = next(unit for unit in units if unit["unit_type"] == "FULLTEXT_PARAGRAPH")

    assert abstract["text"] == "EGFR L858R predicts response."
    assert paragraph["text"] == "Patients with EGFR L858R responded."
    assert paragraph["section"] == "Results"
    assert paragraph["subsection"] == "Patients"
    assert paragraph["document_id"] == "pmcid:PMC-fixture"


def test_real_supplementary_material_caption_is_preserved_as_its_own_source_unit():
    record = _manifest_record("pmcid:PMC2587064")
    units = ReadOnlyDocumentCache(CACHE_ROOT).source_units_for_record(record)
    expected = "Constitutive activation of the PI3K pathway decreases sensitivity of trastuzumab and lapatinib."

    matching = [unit for unit in units if unit["unit_type"] == "SUPPLEMENTARY_CAPTION" and expected in unit["text"]]

    assert matching
    assert all(unit["document_id"] == record["document_id"] for unit in matching)
    assert not any(unit["unit_type"] == "FULLTEXT_PARAGRAPH" and expected in unit["text"] for unit in units)

    unit = matching[0]
    by_id = {source_unit["source_unit_id"]: source_unit for source_unit in units}
    result = validate_enrichment_v3(
        "V3_TRANSPORT_VALID",
        {"decision": "QUOTE", "source_unit_id": unit["source_unit_id"], "quote": unit["text"]},
        candidate={},
        paper_bundle={"document_id": record["document_id"], "source_unit_ids": [unit["source_unit_id"]]},
        source_units_by_id=by_id,
    )
    assert result["outcome"] == "ENRICHMENT_V3_ACCEPTED"
