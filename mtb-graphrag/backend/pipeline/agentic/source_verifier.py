"""Verifica multilivello claim→record curato→fonte PubMed."""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.pipeline.agentic.applicability_validator import (
    normalize_line_category,
    normalize_prior_therapy_requirement,
    normalize_setting_category,
    validate_applicability,
)


SOURCE_VERIFIER_SYSTEM = """Sei un verificatore di evidenze per un Molecular Tumor Board.
Per ogni elemento produci DUE giudizi indipendenti — non fonderli in uno solo.

1) SUPPORTO DOCUMENTALE (source_support_status/source_support_reason)
Valuta se la scheda CIViC e l'abstract PubMed sostengono la CLAIM così come la
FONTE stessa la descrive: popolazione studiata, linea/setting, trattamenti
precedenti e co-biomarker richiesti dalla fonte fanno parte del contesto della
claim da verificare, non vanno ignorati. Esempio corretto di claim
contestualizzata: "osimertinib mostra attività in NSCLC EGFR T790M dopo
progressione a un precedente EGFR-TKI". Non riscrivere la claim usando i dati
del paziente (non diventa "osimertinib supportato per L858R in prima linea").
Il fatto che il PMID esista non basta: controlla esplicitamente
variante/biomarker, farmaco o combinazione, tumore, significatività e
statement CIViC contro l'abstract.
Usa "supported" solo se la fonte sostiene direttamente il proprio record
contestualizzato. Usa "unsupported" SOLO quando la fonte è disponibile e
CONTRADDICE realmente biomarker, farmaco, tumore o claim. Se il PMID è
assente/invalido, l'abstract non è disponibile, i dati sono insufficienti o la
verifica non può essere completata, usa "uncertain" — non "unsupported": un
dato mancante non è una contraddizione.
Se ricavabili dalla fonte, riporta anche source_population, source_line,
source_setting, source_prerequisites (stringhe brevi, per l'oncologo); lascia
questi campi `null` quando la fonte non li specifica — non inventarli mai.
Riporta anche source_interventions: l'elenco completo dei singoli farmaci/
interventi del regime descritto dalla fonte (es. ["amivantamab",
"carboplatino", "pemetrexed"]); lascialo vuoto se non determinabile.

Riporta inoltre, in aggiunta alle stringhe descrittive sopra, tre campi
categorici (per il confronto deterministico, non sostituiscono le stringhe):
- source_line_category: uno tra "first_line", "later_line",
  "post_progression", "adjuvant", "unknown".
- source_setting_category: uno tra "resected", "locally_advanced",
  "metastatic", "recurrent", "adjuvant", "unknown".
- source_prior_therapy_requirement: uno tra "treatment_naive",
  "previously_treated", "specific_therapy", "unknown".
Usa "unknown" quando la fonte non lo specifica esplicitamente: non dedurre.

2) APPLICABILITÀ AL CASO (applicability_status/applicability_reason)
Confronta il contesto appena estratto dalla fonte (punto 1) con il contesto
clinico dichiarato dal paziente ("requested_case"). Questo è un confronto
separato dal supporto documentale: una fonte può sostenere perfettamente il
proprio record e restare comunque non applicabile al caso richiesto.
Non dedurre che "first-line" significhi automaticamente malattia metastatica
o viceversa. Non assumere assenza di terapie pregresse o co-alterazioni
quando il campo del paziente è vuoto: un dato non dichiarato è sconosciuto,
non negativo.
Usa "not_compatible" solo quando il setting/linea della fonte confligge
ESPLICITAMENTE col contesto richiesto (es. fonte solo post-progressione o di
linea successiva contro una richiesta dichiarata first-line-naive).
Usa "indeterminate" quando mancano dati per decidere da un lato o dall'altro.
Usa "compatible" solo quando entrambi i lati dichiarano esplicitamente
setting/linea coincidenti — mai come default.

Non aggiungere conoscenza esterna. Scrivi sempre le motivazioni in italiano.

Restituisci esclusivamente un array JSON, un oggetto per elemento:
[{"index": 0,
  "source_support_status": "supported|unsupported|uncertain",
  "source_support_reason": "...",
  "source_population": "..." o null,
  "source_line": "..." o null,
  "source_setting": "..." o null,
  "source_prerequisites": "..." o null,
  "source_interventions": ["farmaco1", "farmaco2"],
  "source_line_category": "first_line|later_line|post_progression|adjuvant|unknown",
  "source_setting_category": "resected|locally_advanced|metastatic|recurrent|adjuvant|unknown",
  "source_prior_therapy_requirement": "treatment_naive|previously_treated|specific_therapy|unknown",
  "applicability_status": "compatible|indeterminate|not_compatible",
  "applicability_reason": "..."}]
"""


@dataclass
class SourceVerification:
    index: int
    source_support_status: str
    source_support_reason: str
    source_population: str | None
    source_line: str | None
    source_setting: str | None
    source_prerequisites: str | None
    applicability_status: str
    applicability_reason: str
    verification_level: str
    requires_source_review: bool
    requires_clinical_review: bool
    # Categorie strutturate per il confronto deterministico (validate contro
    # uno schema fisso; "unknown" quando non ricavabili o non conformi) —
    # affiancano, senza sostituirle, le stringhe descrittive sopra.
    source_line_category: str = "unknown"
    source_setting_category: str = "unknown"
    source_prior_therapy_requirement: str = "unknown"
    # Regime completo dichiarato dalla fonte (es. ["amivantamab",
    # "carboplatino", "pemetrexed"]), usato per verificare che una claim su
    # una combinazione parziale non venga confermata come regime equivalente.
    source_interventions: list[str] = field(default_factory=list)


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


ParsedResult = tuple[
    str, str, str | None, str | None, str | None, str | None, str, str,
    str, str, str, list[str],
]


def _parse_results(content: Any) -> dict[int, ParsedResult]:
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

    def _optional_text(value: Any) -> str | None:
        return str(value) if isinstance(value, str) and value.strip() else None

    def _interventions(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(entry).strip() for entry in value if isinstance(entry, str) and entry.strip()]

    return {
        int(result["index"]): (
            str(result["source_support_status"]).lower(),
            str(result.get("source_support_reason", "")),
            _optional_text(result.get("source_population")),
            _optional_text(result.get("source_line")),
            _optional_text(result.get("source_setting")),
            _optional_text(result.get("source_prerequisites")),
            str(result["applicability_status"]).lower(),
            str(result.get("applicability_reason", "")),
            normalize_line_category(result.get("source_line_category")),
            normalize_setting_category(result.get("source_setting_category")),
            normalize_prior_therapy_requirement(result.get("source_prior_therapy_requirement")),
            _interventions(result.get("source_interventions")),
        )
        for result in parsed
    }


def _batch_size() -> int:
    try:
        return min(8, max(1, int(os.getenv("SOURCE_VERIFIER_BATCH_SIZE", "4"))))
    except ValueError:
        return 4


def _max_workers() -> int:
    """Concorrenza dei batch iniziali verso l'endpoint LLM. Predefinita a 1:
    con un singolo endpoint (es. Ollama locale) una concorrenza più alta può
    sovraccaricare il servizio e causare fallimenti a cascata."""
    try:
        return max(1, min(8, int(os.getenv("SOURCE_VERIFIER_MAX_WORKERS", "1"))))
    except ValueError:
        return 1


def _retry_timeout_seconds() -> int:
    try:
        return max(1, int(os.getenv("SOURCE_VERIFIER_RETRY_TIMEOUT_SECONDS", "15")))
    except ValueError:
        return 15


def _retry_max_workers() -> int:
    """Concorrenza del retry bounded a singolo record. Predefinita a 1, per
    lo stesso motivo di ``_max_workers``."""
    try:
        return max(1, min(4, int(os.getenv("SOURCE_VERIFIER_RETRY_MAX_WORKERS", "1"))))
    except ValueError:
        return 1


def _verification_batches(payload: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    size = _batch_size()
    return [payload[start:start + size] for start in range(0, len(payload), size)]


def _invoke_verifier_batch(
    llm_client: Any,
    batch: list[dict[str, Any]],
) -> tuple[dict[int, ParsedResult], str | None]:
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


def _invoke_verifier_single_with_timeout(
    llm_client: Any,
    entry: dict[str, Any],
    timeout_seconds: int,
) -> tuple[dict[int, ParsedResult], str | None]:
    """Un solo record per chiamata, con timeout configurabile indipendente dal
    batching iniziale — usato esclusivamente dal retry bounded, mai da un
    ciclo di retry infinito."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_invoke_verifier_batch, llm_client, [entry])
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        return {}, "timeout del modello"
    finally:
        executor.shutdown(wait=False)


def _retry_missing_items(
    llm_client: Any,
    payload_by_index: dict[int, dict[str, Any]],
    missing_indices: set[int],
) -> tuple[dict[int, ParsedResult], dict[int, str]]:
    """Un solo retry, bounded: batch da un singolo record, concorrenza
    limitata, timeout configurabile. Nessun retry infinito: gli indici che
    falliscono anche qui restano falliti e degradano a 'uncertain' a monte."""
    retry_entries = [payload_by_index[index] for index in sorted(missing_indices) if index in payload_by_index]
    results: dict[int, ParsedResult] = {}
    failures: dict[int, str] = {}
    if not retry_entries:
        return results, failures

    timeout_seconds = _retry_timeout_seconds()
    workers = min(_retry_max_workers(), len(retry_entries))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_invoke_verifier_single_with_timeout, llm_client, entry, timeout_seconds): entry
            for entry in retry_entries
        }
        for future in as_completed(futures):
            entry = futures[future]
            entry_results, failure = future.result()
            results.update(entry_results)
            if failure:
                failures[int(entry["index"])] = failure
    return results, failures


def _verification(
    *,
    index: int,
    source_support_status: str,
    source_support_reason: str,
    verification_level: str,
    source_population: str | None = None,
    source_line: str | None = None,
    source_setting: str | None = None,
    source_prerequisites: str | None = None,
    applicability_status: str = "indeterminate",
    applicability_reason: str = "",
    source_line_category: str = "unknown",
    source_setting_category: str = "unknown",
    source_prior_therapy_requirement: str = "unknown",
    source_interventions: list[str] | None = None,
) -> SourceVerification:
    """Costruisce un esito derivando i due flag di revisione dai due assi."""
    return SourceVerification(
        index=index,
        source_support_status=source_support_status,
        source_support_reason=source_support_reason,
        source_population=source_population,
        source_line=source_line,
        source_setting=source_setting,
        source_prerequisites=source_prerequisites,
        applicability_status=applicability_status,
        applicability_reason=applicability_reason,
        verification_level=verification_level,
        requires_source_review=source_support_status in {"uncertain", "unsupported"},
        requires_clinical_review=applicability_status in {"indeterminate", "not_compatible"},
        source_line_category=source_line_category,
        source_setting_category=source_setting_category,
        source_prior_therapy_requirement=source_prior_therapy_requirement,
        source_interventions=list(source_interventions) if source_interventions else [],
    )


def _regimen_components(text: str) -> set[str]:
    parts = re.split(r"[+,/]|(?:\band\b)", text or "", flags=re.IGNORECASE)
    return {part.strip().lower() for part in parts if part.strip()}


_REGIMEN_CHAIN_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9-]{3,}(?:\s*(?:\+|,|/|\bplus\b|\band\b|\be\b)\s*[A-Za-z][A-Za-z0-9-]{3,})+",
    re.IGNORECASE,
)

# Parole generiche che compaiono spesso in catene testuali connesse da "and"/
# "plus"/virgole ma non sono nomi di farmaci: escluse per ridurre i falsi
# positivi della scansione testuale diretta (non un dizionario di farmaci).
_REGIMEN_CHAIN_STOPWORDS = {
    "and", "the", "with", "efficacy", "safety", "survival", "progression",
    "free", "overall", "response", "rate", "rates", "phase", "study",
    "trial", "patients", "patient", "advanced", "metastatic", "previously",
    "treated", "therapy", "treatment", "group", "groups", "arm", "arms",
    "randomized", "randomised", "results", "significant", "significantly",
    "compared", "versus", "placebo", "standard", "care", "chemotherapy",
    "combination", "regimen", "cohort", "analysis", "outcome", "outcomes",
    "median", "follow", "months", "years", "clinical", "disease", "line",
    "first", "second", "later", "based", "receiving", "received",
}


def _regimen_phrase_components(text: str) -> set[str]:
    """Cerca catene di token separati da connettori (+, virgola, 'and',
    'plus', ecc.) nel testo grezzo PubMed/CIViC — un'euristica indipendente
    dall'LLM per individuare un regime a più farmaci descritto nel titolo/
    abstract anche quando ``source_interventions`` non lo riporta."""
    components: set[str] = set()
    for match in _REGIMEN_CHAIN_PATTERN.finditer(text or ""):
        for token in re.split(r"\s*(?:\+|,|/|\bplus\b|\band\b|\be\b)\s*", match.group(0), flags=re.IGNORECASE):
            normalized = token.strip().lower()
            if normalized and normalized not in _REGIMEN_CHAIN_STOPWORDS:
                components.add(normalized)
    return components


def _regimen_check_reason(item: Any, source_interventions: list[str], source_text: str) -> str | None:
    """Fail-closed: una claim a più farmaci non resta "supported" senza
    riserva se il regime completo della fonte non è verificabile o include
    componenti aggiuntivi — sia che manchino da ``source_interventions``
    (l'LLM può ometterli), sia che siano presenti solo nel testo grezzo
    PubMed/CIViC disponibile, che viene sempre riscansionato indipendentemente
    dalla motivazione dichiarata dall'LLM."""
    claim_components = _regimen_components(item.object)
    if len(claim_components) < 2:
        return None  # non è una claim di regime combinato: nessun controllo necessario

    source_components = {value.strip().lower() for value in source_interventions if value and value.strip()}
    if not source_components:
        return (
            "La claim descrive un regime a più farmaci "
            f"({', '.join(sorted(claim_components))}), ma la fonte non ha riportato un elenco "
            "verificabile del regime completo: il supporto documentale non può essere confermato "
            "senza riserva su una combinazione parziale."
        )

    missing_from_source_list = source_components - claim_components
    if missing_from_source_list:
        return (
            "La fonte descrive il regime completo "
            f"({', '.join(sorted(source_components))}), che include "
            f"{', '.join(sorted(missing_from_source_list))} non presenti nella claim: il supporto "
            "documentale non copre la combinazione parziale come regime equivalente."
        )

    missing_from_text = _regimen_phrase_components(source_text) - claim_components - source_components
    if missing_from_text:
        return (
            "Il testo della fonte (titolo/abstract) menziona componenti aggiuntivi del regime "
            f"({', '.join(sorted(missing_from_text))}) non presenti né nella claim né nell'elenco "
            "riportato dal verificatore: il supporto documentale non può essere confermato senza "
            "riserva sulla combinazione parziale."
        )
    return None


def verify_evidence_items(
    items: list[Any],
    *,
    llm_client: Any | None = None,
    source_loader: Callable[[Iterable[int]], dict[int, dict[str, str]]] = fetch_pubmed_sources,
    case_context: dict[str, str] | None = None,
    metrics: dict[str, int] | None = None,
) -> list[SourceVerification]:
    """Verifica in modalità fail-closed: dubbio o fonte assente richiedono revisione.

    ``unsupported`` è riservato ai casi in cui la fonte è disponibile e
    contraddice realmente la claim: nessuno dei controlli strutturali qui
    sotto ha letto un contenuto contraddittorio, quindi producono sempre
    ``uncertain`` quando falliscono, mai ``unsupported``.

    Se ``metrics`` è fornito, viene popolato in-place con contatori
    diagnostici (``verifier_batches``, ``verifier_failed_batches``,
    ``verifier_retry_items``, ``verifier_recovered_items``,
    ``verifier_failed_items``, ``verifier_elapsed_ms``) senza cambiare il tipo
    di ritorno della funzione.
    """
    verification_started = perf_counter()
    if not items:
        if metrics is not None:
            metrics.update(
                verifier_batches=0,
                verifier_failed_batches=0,
                verifier_retry_items=0,
                verifier_recovered_items=0,
                verifier_failed_items=0,
                verifier_elapsed_ms=0,
            )
        return []
    if llm_client is None:
        from backend.pipeline.llm import llm_judge
        llm_client = llm_judge

    structural: dict[int, SourceVerification] = {}
    eligible: list[tuple[int, Any, int]] = []
    for index, item in enumerate(items):
        pmid = _pmid(item.source_id)
        if pmid is None:
            structural[index] = _verification(
                index=index,
                source_support_status="uncertain",
                source_support_reason="Identificatore PMID assente o non valido.",
                verification_level="provenance",
            )
            continue
        if not item.evidence_statement or not item.citation_text:
            structural[index] = _verification(
                index=index,
                source_support_status="uncertain",
                source_support_reason="Il record non contiene statement clinico e citazione sufficienti.",
                verification_level="curated_record",
            )
            continue
        if item.evidence_level not in {"A", "B", "LEVEL_1", "LEVEL_2", "1", "2"}:
            structural[index] = _verification(
                index=index,
                source_support_status="uncertain",
                source_support_reason="Livello di evidenza sotto la soglia del protocollo: dato insufficiente, non una contraddizione.",
                verification_level="clinical_rules",
            )
            continue
        eligible.append((index, item, pmid))

    try:
        pubmed_sources = source_loader(pmid for _, _, pmid in eligible)
    except Exception:
        pubmed_sources = {}

    payload = []
    missing_source: set[int] = set()
    source_text_by_index: dict[int, str] = {}
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
        source_text_by_index[index] = source_text
        subject_anchors = _anchors(item.subject)
        object_anchors = _anchors(item.object)
        if subject_anchors and not any(anchor in source_text for anchor in subject_anchors):
            structural[index] = _verification(
                index=index,
                source_support_status="uncertain",
                source_support_reason="La fonte non contiene gli ancoraggi del biomarker dichiarato nella claim.",
                verification_level="clinical_rules",
            )
            continue
        if object_anchors and not any(anchor in source_text for anchor in object_anchors):
            structural[index] = _verification(
                index=index,
                source_support_status="uncertain",
                source_support_reason="La fonte non contiene l'oggetto clinico dichiarato nella claim.",
                verification_level="clinical_rules",
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

    llm_results: dict[int, ParsedResult] = {}
    llm_failures: dict[int, str] = {}
    batches_run = 0
    failed_batches = 0
    retry_items = 0
    recovered_items = 0
    if payload:
        batches = _verification_batches(payload)
        batches_run = len(batches)
        workers = min(_max_workers(), len(batches))
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
                    failed_batches += 1
                    for entry in batch:
                        llm_failures[int(entry["index"])] = failure

        missing_indices = {
            int(entry["index"]) for entry in payload if int(entry["index"]) not in llm_results
        }
        if missing_indices:
            retry_items = len(missing_indices)
            payload_by_index = {int(entry["index"]): entry for entry in payload}
            retry_results, retry_failures = _retry_missing_items(llm_client, payload_by_index, missing_indices)
            recovered_items = len(retry_results)
            llm_results.update(retry_results)
            for index in missing_indices:
                if index in retry_results:
                    llm_failures.pop(index, None)
                elif index in retry_failures:
                    llm_failures[index] = retry_failures[index]

    failed_items = retry_items - recovered_items
    if metrics is not None:
        metrics.update(
            verifier_batches=batches_run,
            verifier_failed_batches=failed_batches,
            verifier_retry_items=retry_items,
            verifier_recovered_items=recovered_items,
            verifier_failed_items=failed_items,
            verifier_elapsed_ms=int((perf_counter() - verification_started) * 1000),
        )

    results: list[SourceVerification] = []
    for index in range(len(items)):
        if index in structural:
            results.append(structural[index])
            continue
        if index in missing_source:
            results.append(_verification(
                index=index,
                source_support_status="uncertain",
                source_support_reason="Abstract PubMed non disponibile: il record CIViC da solo non chiude la verifica.",
                verification_level="curated_record",
            ))
            continue
        failure = llm_failures.get(index)
        parsed = llm_results.get(index)
        if parsed is None:
            support_status = "uncertain"
            support_reason = (
                "Verifica semantica non completata"
                + (f" ({failure})." if failure else ": esito mancante nella risposta del modello.")
            )
            population = line = setting = prerequisites = None
            applicability_status = "indeterminate"
            applicability_reason = "Applicabilità non valutata: la verifica del supporto documentale non è stata completata."
            line_category = setting_category = prior_requirement = "unknown"
            source_interventions: list[str] = []
        else:
            (
                support_status, support_reason,
                population, line, setting, prerequisites,
                applicability_status, applicability_reason,
                line_category, setting_category, prior_requirement,
                source_interventions,
            ) = parsed
        if support_status not in {"supported", "unsupported", "uncertain"}:
            support_status = "uncertain"
        if applicability_status not in {"compatible", "indeterminate", "not_compatible"}:
            applicability_status = "indeterminate"

        if support_status == "supported":
            regimen_reason = _regimen_check_reason(
                items[index], source_interventions, source_text_by_index.get(index, ""),
            )
            if regimen_reason:
                support_status = "uncertain"
                support_reason = regimen_reason

        applicability_status, applicability_reason = validate_applicability(
            {
                "source_line_category": line_category,
                "source_setting_category": setting_category,
                "source_prior_therapy_requirement": prior_requirement,
            },
            case_context or {},
            applicability_status,
            applicability_reason,
        )

        results.append(_verification(
            index=index,
            source_support_status=support_status,
            source_support_reason=support_reason,
            verification_level="pubmed_abstract",
            source_population=population,
            source_line=line,
            source_setting=setting,
            source_prerequisites=prerequisites,
            applicability_status=applicability_status,
            applicability_reason=applicability_reason,
            source_line_category=line_category,
            source_setting_category=setting_category,
            source_prior_therapy_requirement=prior_requirement,
            source_interventions=source_interventions,
        ))
    return results
