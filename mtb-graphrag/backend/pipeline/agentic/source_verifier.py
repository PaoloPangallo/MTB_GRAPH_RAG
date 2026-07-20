"""Verifica multilivello claim→record curato→fonte PubMed."""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOURCE_VERIFIER_SYSTEM = """Sei un verificatore di evidenze per un Molecular Tumor Board.
Per ogni elemento valuta se la CLAIM è sostenuta dalla scheda CIViC e dall'abstract
PubMed forniti. Controlla esplicitamente variante/biomarker, significatività,
tumore, oggetto della claim e contesto clinico richiesto, inclusa la linea
terapeutica. Il fatto che il PMID esista non basta. Una fonte adiuvante,
post-progressione o di linea successiva non supporta una claim presentata come
prima linea, a meno che il record dimostri direttamente anche quel contesto.
Non dedurre che "first-line" significhi automaticamente malattia metastatica:
se stadio o setting non sono dichiarati e la distinzione dipende proprio da
questi dati, usa "uncertain" e richiedi revisione umana.

Usa "supported" solo se il supporto è diretto. Usa "unsupported" se la fonte
contraddice la claim o riguarda entità cliniche diverse. Usa "uncertain" se i
dati non bastano. Non aggiungere conoscenza esterna.
Scrivi sempre la motivazione in italiano.

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


def _content_text(content: Any) -> str:
    """Normalizza stringhe e content block restituiti dai client LangChain."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in ("text", "content", "output"):
            if isinstance(content.get(key), str):
                return content[key].strip()
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, list):
        blocks = []
        for block in content:
            if isinstance(block, str):
                blocks.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                blocks.append(block["text"])
        if blocks:
            return "\n".join(blocks).strip()
        return json.dumps(content, ensure_ascii=False)
    return str(content).strip()


def _parse_results(content: Any) -> dict[int, tuple[str, str]]:
    if isinstance(content, list) and all(
        isinstance(result, dict) and "index" in result for result in content
    ):
        parsed: Any = content
    elif isinstance(content, dict) and "results" in content:
        parsed = content["results"]
    else:
        text = _content_text(content)
        fenced = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            array = re.search(r"\[.*\]", text, flags=re.DOTALL)
            obj = re.search(r"\{.*\}", text, flags=re.DOTALL)
            candidate = array or obj
            if candidate:
                text = candidate.group(0)
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("results", [parsed])
    if not isinstance(parsed, list):
        raise ValueError("Il verificatore non ha restituito una lista di esiti")
    return {
        int(result["index"]): (
            str(result["verdict"]).lower(),
            str(result.get("reason", "")),
        )
        for result in parsed
    }


def _batch_size() -> int:
    try:
        return min(8, max(1, int(os.getenv("SOURCE_VERIFIER_BATCH_SIZE", "4"))))
    except ValueError:
        return 4


def _verification_batches(payload: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    size = _batch_size()
    return [payload[start:start + size] for start in range(0, len(payload), size)]


def _invoke_verifier_batch(
    llm_client: Any,
    batch: list[dict[str, Any]],
) -> tuple[dict[int, tuple[str, str]], str | None]:
    try:
        response = llm_client.invoke([
            ("system", SOURCE_VERIFIER_SYSTEM),
            ("human", json.dumps(batch, ensure_ascii=False, sort_keys=True)),
        ])
        return _parse_results(response.content), None
    except TimeoutError:
        return {}, "timeout del modello"
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {}, "risposta non conforme al formato JSON"
    except Exception:
        return {}, "errore del servizio LLM"


def verify_evidence_items(
    items: list[Any],
    *,
    llm_client: Any | None = None,
    source_loader: Callable[[Iterable[int]], dict[int, dict[str, str]]] = fetch_pubmed_sources,
    case_context: dict[str, str] | None = None,
) -> list[SourceVerification]:
    """Verifica in modalità fail-closed: dubbio o fonte assente richiedono revisione."""
    if not items:
        return []
    if llm_client is None:
        from backend.pipeline.llm import llm_judge
        llm_client = llm_judge

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
            "requested_case": case_context or {},
            "civic_record": {
                "evidence_level": item.evidence_level,
                "evidence_statement": item.evidence_statement,
                "citation_text": item.citation_text,
            },
            "pubmed": source,
        })

    llm_results: dict[int, tuple[str, str]] = {}
    llm_failures: dict[int, str] = {}
    if payload:
        batches = _verification_batches(payload)
        workers = min(4, len(batches))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_invoke_verifier_batch, llm_client, batch): batch
                for batch in batches
            }
            for future in as_completed(futures):
                batch = futures[future]
                batch_results, failure = future.result()
                llm_results.update(batch_results)
                if failure:
                    for entry in batch:
                        llm_failures[int(entry["index"])] = failure

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
        failure = llm_failures.get(index)
        verdict, reason = llm_results.get(index, (
            "uncertain",
            "Verifica semantica non completata"
            + (f" ({failure})." if failure else ": esito mancante nella risposta del modello."),
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
