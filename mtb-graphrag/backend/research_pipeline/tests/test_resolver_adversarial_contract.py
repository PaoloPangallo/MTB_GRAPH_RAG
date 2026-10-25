from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache


def test_pubmed_doi_from_references_is_not_selected():
    payload = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>T</ArticleTitle></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1000/main</ArticleId></ArticleIdList><ReferenceList><Reference><ArticleIdList><ArticleId IdType="doi">10.1000/reference</ArticleId></ArticleIdList></Reference></ReferenceList></PubmedData></PubmedArticle></PubmedArticleSet>'''
    fields, _ = AuthorizedDocumentCache._pubmed_xml_fields(payload, "1")
    assert fields["doi"] == "10.1000/main"


def test_pubmed_multi_record_selects_requested_identity():
    payload = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>one</ArticleTitle></Article></MedlineCitation></PubmedArticle><PubmedArticle><MedlineCitation><PMID>2</PMID><Article><ArticleTitle>two</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'''
    fields, _ = AuthorizedDocumentCache._pubmed_xml_fields(payload, "2")
    assert fields["title"] == "two"


def test_pmc_generic_reference_pmid_is_not_identity():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "x.xml"
        path.write_text("<article><front><article-meta><article-id pub-id-type='doi'>10/x</article-id></article-meta></front><ref-list><ref><pmid>999</pmid></ref></ref-list></article>", encoding="utf-8")
        cache = AuthorizedDocumentCache(root, network=False)
        assert cache._pmc_article_pmid({"local_cache_path": "x.xml"}) is None


def test_pmc_article_meta_pmid_is_identity():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "x.xml"
        path.write_text("<article><front><article-meta><article-id pub-id-type='pmid'>123</article-id></article-meta></front><ref-list><ref><pmid>999</pmid></ref></ref-list></article>", encoding="utf-8")
        cache = AuthorizedDocumentCache(root, network=False)
        assert cache._pmc_article_pmid({"local_cache_path": "x.xml"}) == "123"
