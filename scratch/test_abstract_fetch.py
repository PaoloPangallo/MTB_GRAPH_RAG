import requests
import xml.etree.ElementTree as ET

def fetch_pubmed_abstracts(pmids: list[str]) -> dict[str, dict]:
    if not pmids:
        return {}
    ids_str = ",".join(pmids)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        results = {}
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            if pmid_el is None:
                continue
            pmid = pmid_el.text
            title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else ""
            abstract_el = article.find(".//Abstract")
            abstract_texts = []
            if abstract_el is not None:
                for text_el in abstract_el.findall(".//AbstractText"):
                    abstract_texts.append("".join(text_el.itertext()))
            abstract = " ".join(abstract_texts)
            results[pmid] = {
                "title": title,
                "abstract": abstract
            }
        return results
    except Exception as e:
        print(f"Error fetching abstracts: {e}")
        return {}

if __name__ == "__main__":
    test_pmids = ["15651334", "37937763"]
    res = fetch_pubmed_abstracts(test_pmids)
    for pmid, info in res.items():
        print(f"PMID: {pmid}")
        print(f"Title: {info['title']}")
        print(f"Abstract length: {len(info['abstract'])} chars")
        print(f"Abstract snippet: {info['abstract'][:150]}...")
        print("-" * 40)
