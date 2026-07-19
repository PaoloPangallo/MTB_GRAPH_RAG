"""Verifica multilivello claim→record curato→fonte PubMed."""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOURCE_VERIFIER_SYSTEM = """Sei un verificatore di evidenze per un Molecular Tumor Board.
Per ogni elemento valuta se la CLAIM è sostenuta dalla scheda CIViC e dall'abstract
PubMed forniti. Controlla esplicitamente variante/biomarker, significatività,
tumore e oggetto della claim. Il fatto che il PMID esista non basta.

Usa "supported" solo se il supporto è diretto. Usa "unsupported" se la fonte
contraddice la claim o riguarda entità cliniche diverse. Usa "uncertain" se i
dati non bastano. Non aggiungere conoscenza esterna.

Restituisci esclusivamente un array JSON:
[{"index": 0, "verdict": "supported|unsupported|uncertain", "reason": "..."}]
"""


@dataclass
class SourceVerification:
    index: int
    verdict: str
    reason: str
    verification_level: str
    requires_human_review: bool


def _pmid(source_id: str | None) -> int | None:
    match = re.fullmatch(r"PMID:(\d{5,9})", source_id or "")
    return int(match.group(1)) if match else None


def _text(element: ET.Element | None) -> str:
    return "" if element is None else "".join(element.itertext()).strip()


def fetch_pubmed_sources(pmids: Iterable[int]) -> dict[int, dict[str, str]]:
    unique = sorted(set(pmids))
    if not unique:
        return {}
    query = urlencode({
        "db": "pubmed",
        "id": ",".join(str(pmid) for pmid in unique),
        "retmode": "xml",
    })
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{query}"
    contact = os.getenv("NCBI_EMAIL", "research@example.invalid")
    request = Request(url, headers={"User-Agent": f"MTB-GraphRAG/1.0 ({contact})"})
    with urlopen(request, timeout=12) as response:
        content = response.read()
    root = ET.fromstring(content)
    sources: dict[int, dict[str, str]] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_text = _text(article.find(".//MedlineCitation/PMID"))
        if not pmid_text.isdigit():
            continue
        abstract_parts = [
            _text(node)
            for node in article.findall(".//Article/Abstract/AbstractText")
            if _text(node)
        ]
        sources[int(pmid_text)] = {
            "title": _text(article.find(".//Article/ArticleTitle")),
            "abstract": " ".join(abstract_parts),
        }
    return sources


def _claim(item: Any) -> str:
    return f"{item.subject} — {item.relation} — {item.object} ({item.context})."


def _anchors(text: str) -> set[str]:
    stopwords = {
        "association", "clinical", "evidence", "profile", "response",
        "sensitivity", "resistance", "variant",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]+", text or "")
        if len(token) >= 3 and token.lower() not in stopwords
    }


def _parse_results(content: Any) -> dict[int, tuple[str, str]]:
    text = str(content).strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        candidate = re.search(r"\[.*\]", text, flags=re.DOTALL)
        if candidate:
            text = candidate.group(0)
    parsed = json.loads(text)
    return {
        int(result["index"]): (
            str(result["verdict"]).lower(),
            str(result.get("reason", "")),
        )
        for result in parsed
    }


def verify_evidence_items(
    items: list[Any],
    *,
    llm_client: Any | None = None,
    source_loader: Callable[[Iterable[int]], dict[int, dict[str, str]]] = fetch_pubmed_sources,
) -> list[SourceVerification]:
    """Verifica in modalità fail-closed: dubbio o fonte assente richiedono revisione."""
    if not items:
        return []
    if llm_client is None:
        from backend.pipeline.llm import llm
        llm_client = llm

    structural: dict[int, SourceVerification] = {}
    eligible: list[tuple[int, Any, int]] = []
    for index, item in enumerate(items):
        pmid = _pmid(item.source_id)
        if pmid is None:
            structural[index] = SourceVerification(
                index=index,
                verdict="unsupported",
                reason="Identificatore PMID assente o non valido.",
                verification_level="provenance",
                requires_human_review=True,
            )
            continue
        if not item.evidence_statement or not item.citation_text:
            structural[index] = SourceVerification(
                index=index,
                verdict="uncertain",
                reason="Il record non contiene statement clinico e citazione sufficienti.",
                verification_level="curated_record",
                requires_human_review=True,
            )
            continue
        if item.evidence_level not in {"A", "B", "LEVEL_1", "LEVEL_2", "1", "2"}:
            structural[index] = SourceVerification(
                index=index,
                verdict="unsupported",
                reason="Livello di evidenza non ammesso dal protocollo.",
                verification_level="clinical_rules",
                requires_human_review=True,
            )
            continue
        eligible.append((index, item, pmid))

    try:
        pubmed_sources = source_loader(pmid for _, _, pmid in eligible)
    except Exception:
        pubmed_sources = {}

    payload = []
    missing_source: set[int] = set()
    for index, item, pmid in eligible:
        source = pubmed_sources.get(pmid)
        if not source or not source.get("abstract"):
            missing_source.add(index)
            continue
        source_text = " ".join((
            item.evidence_statement or "",
            item.citation_text or "",
            source.get("title", ""),
            source.get("abstract", ""),
        )).lower()
        subject_anchors = _anchors(item.subject)
        object_anchors = _anchors(item.object)
        if subject_anchors and not any(anchor in source_text for anchor in subject_anchors):
            structural[index] = SourceVerification(
                index=index,
                verdict="uncertain",
                reason="La fonte non contiene gli ancoraggi del biomarker dichiarato nella claim.",
                verification_level="clinical_rules",
                requires_human_review=True,
            )
            continue
        if object_anchors and not any(anchor in source_text for anchor in object_anchors):
            structural[index] = SourceVerification(
                index=index,
                verdict="uncertain",
                reason="La fonte non contiene l'oggetto clinico dichiarato nella claim.",
                verification_level="clinical_rules",
                requires_human_review=True,
            )
            continue
        payload.append({
            "index": index,
            "claim": _claim(item),
            "civic_record": {
                "evidence_level": item.evidence_level,
                "evidence_statement": item.evidence_statement,
                "citation_text": item.citation_text,
            },
            "pubmed": source,
        })

    llm_results: dict[int, tuple[str, str]] = {}
    if payload:
        try:
            response = llm_client.invoke([
                ("system", SOURCE_VERIFIER_SYSTEM),
                ("human", json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            ])
            llm_results = _parse_results(response.content)
        except Exception:
            llm_results = {}

    results: list[SourceVerification] = []
    for index in range(len(items)):
        if index in structural:
            results.append(structural[index])
            continue
        if index in missing_source:
            results.append(SourceVerification(
                index=index,
                verdict="uncertain",
                reason="Abstract PubMed non disponibile: il record CIViC da solo non chiude la verifica.",
                verification_level="curated_record",
                requires_human_review=True,
            ))
            continue
        verdict, reason = llm_results.get(index, (
            "uncertain",
            "Il verificatore semantico non ha restituito un esito valido.",
        ))
        if verdict not in {"supported", "unsupported", "uncertain"}:
            verdict = "uncertain"
        results.append(SourceVerification(
            index=index,
            verdict=verdict,
            reason=reason,
            verification_level="pubmed_abstract",
            requires_human_review=verdict != "supported",
        ))
    return results
