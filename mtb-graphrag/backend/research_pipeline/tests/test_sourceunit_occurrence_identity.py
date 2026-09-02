from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache, finalize_source_unit_occurrence_ids
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.documents.live_resolution import DocumentResolution, ResolvedDocument, load_source_units


def test_identical_occurrences_receive_distinct_deterministic_ids():
    units = [
        {"source_unit_id": "old", "content_hash": "old", "document_id": "pmid:1", "unit_type": "TABLE_CELL", "text": "same", "section": "A"},
        {"source_unit_id": "old", "content_hash": "old", "document_id": "pmid:1", "unit_type": "TABLE_CELL", "text": "same", "section": "A"},
    ]
    first = finalize_source_unit_occurrence_ids("pmid:1", units)
    second = finalize_source_unit_occurrence_ids("pmid:1", units)
    assert first[0]["text"] == first[1]["text"] == "same"
    assert first[0]["source_unit_id"] != first[1]["source_unit_id"]
    assert first[0]["content_hash"] == first[1]["content_hash"] == "old"
    assert [x["content_hash"] for x in first] == [x["content_hash"] for x in units]
    assert [x["source_unit_id"] for x in first] == [x["source_unit_id"] for x in second]


def test_document_namespace_preserves_cross_consumer_reuse():
    unit = [{"source_unit_id": "old", "content_hash": "old", "document_id": "pmid:1", "unit_type": "ABSTRACT", "text": "x"}]
    assert finalize_source_unit_occurrence_ids("pmid:1", unit)[0]["source_unit_id"] == finalize_source_unit_occurrence_ids("pmid:1", unit)[0]["source_unit_id"]


def test_jats_table_cells_survive_id_index_and_validator(tmp_path):
    cache = AuthorizedDocumentCache(root=tmp_path, network=False)
    xml = '''<article><body><sec><title>Results</title><table-wrap><table><tr><td>IDENTICAL EVIDENCE TEXT</td><td>IDENTICAL EVIDENCE TEXT</td></tr></table></table-wrap></sec></body></article>'''
    path = tmp_path / "pmc/xml/test.xml"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(xml)
    record = {"document_id": "pmcid:PMC1", "availability": "PMC_XML_AVAILABLE", "local_cache_path": "pmc/xml/test.xml"}
    units = cache.source_units_for_record(record)
    cells = [u for u in units if u["unit_type"] == "TABLE_CELL"]
    assert len(cells) == 2 and cells[0]["text"] == cells[1]["text"]
    assert cells[0]["source_unit_id"] != cells[1]["source_unit_id"]
    indexed = {u["source_unit_id"]: u for u in units}
    assert len(indexed) == len(units)
    second = cells[1]
    result = validate_enrichment_v3("V3_TRANSPORT_VALID", {"decision": "QUOTE", "source_unit_id": second["source_unit_id"], "quote": second["text"]}, candidate={}, paper_bundle={"document_id": "pmcid:PMC1", "source_unit_ids": list(indexed)}, source_units_by_id=indexed)
    assert result["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    assert indexed[second["source_unit_id"]] is second

    resolution = DocumentResolution((ResolvedDocument("pmcid:PMC1", "b", "c", "PMC_XML_AVAILABLE", True, True, "FULL_TEXT_ARTICLE", None, False, False, True, None, (), {}),), "cache", None)
    bundle = load_source_units(resolution, {"pmcid:PMC1": record}, cache)
    assert len(bundle.units_by_id) == len(units)
    assert second["source_unit_id"] in bundle.units_by_id
    loaded_second = bundle.units_by_id[second["source_unit_id"]]
    first = cells[0]
    assert (first["row"], first["column"]) != (second["row"], second["column"])
    for field in ("source_unit_id", "document_id", "unit_type", "section", "row", "column", "text", "content_hash"):
        assert loaded_second.get(field) == second.get(field)
    real_result = validate_enrichment_v3("V3_TRANSPORT_VALID", {"decision": "QUOTE", "source_unit_id": second["source_unit_id"], "quote": second["text"]}, candidate={}, paper_bundle={"document_id": "pmcid:PMC1", "source_unit_ids": list(bundle.units_by_id)}, source_units_by_id=bundle.units_by_id)
    assert real_result["outcome"] == "ENRICHMENT_V3_ACCEPTED"


def test_pubmed_path_preserves_non_id_fields_and_is_deterministic(tmp_path):
    cache = AuthorizedDocumentCache(root=tmp_path, network=False)
    xml = '''<PubmedArticleSet><PubmedArticle><MedlineCitation><Article><ArticleTitle>Title</ArticleTitle><Abstract><AbstractText>Evidence text.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'''
    path = tmp_path / "pubmed/abstracts/test.xml"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(xml)
    record = {"document_id": "pmid:1", "availability": "ABSTRACT_AVAILABLE", "local_cache_path": "pubmed/abstracts/test.xml"}
    a, b = cache.source_units_for_record(record), cache.source_units_for_record(record)
    assert [(u["source_unit_id"], u["content_hash"], u["text"], u["unit_type"], u.get("section")) for u in a] == [(u["source_unit_id"], u["content_hash"], u["text"], u["unit_type"], u.get("section")) for u in b]


def test_jats_figure_captions_survive_real_runtime_path(tmp_path):
    cache = AuthorizedDocumentCache(root=tmp_path, network=False)
    xml = '''<article><body><sec><title>R</title><fig><caption><p>Repeated caption</p></caption></fig><fig><caption><p>Repeated caption</p></caption></fig></sec></body></article>'''
    path = tmp_path / "pmc/xml/caption.xml"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(xml)
    record = {"document_id": "pmcid:PMC2", "availability": "PMC_XML_AVAILABLE", "local_cache_path": "pmc/xml/caption.xml"}
    units = cache.source_units_for_record(record); caps = [u for u in units if u["unit_type"] == "FIGURE_CAPTION"]
    assert len(caps) == 2 and caps[0]["text"] == caps[1]["text"] and caps[0]["source_unit_id"] != caps[1]["source_unit_id"]
    resolution = DocumentResolution((ResolvedDocument("pmcid:PMC2", "b", "c", "PMC_XML_AVAILABLE", True, True, "FULL_TEXT_ARTICLE", None, False, False, True, None, (), {}),), "cache", None)
    assert len(load_source_units(resolution, {"pmcid:PMC2": record}, cache).units_by_id) == len(units)


def test_pdf_path_finalizes_repeated_occurrences(tmp_path):
    from reportlab.pdfgen import canvas
    cache = AuthorizedDocumentCache(root=tmp_path, network=False)
    path = tmp_path / "pdf/test.pdf"; path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path)); pdf.drawString(72, 720, "IDENTICAL PDF EVIDENCE"); pdf.showPage(); pdf.drawString(72, 720, "IDENTICAL PDF EVIDENCE"); pdf.save()
    record = {"document_id": "local:pdf1", "availability": "LOCAL_PDF_AVAILABLE", "local_cache_path": "pdf/test.pdf"}
    a, b = cache.source_units_for_record(record), cache.source_units_for_record(record)
    assert len(a) == 2 and a[0]["text"] == a[1]["text"]
    assert a[0]["source_unit_id"] != a[1]["source_unit_id"]
    assert [(x["source_unit_id"], x["content_hash"], x["text"]) for x in a] == [(x["source_unit_id"], x["content_hash"], x["text"]) for x in b]
    resolution = DocumentResolution((ResolvedDocument("local:pdf1", "b", "c", "LOCAL_PDF_AVAILABLE", True, True, "LOCAL_PDF", None, False, False, True, None, (), {}),), "cache", None)
    assert len(load_source_units(resolution, {"local:pdf1": record}, cache).units_by_id) == 2
