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
    derive_applicability,
    normalize_line_category,
    normalize_prior_therapy_requirement,
    normalize_setting_category,
    validate_applicability,
)
from backend.pipeline.agentic.regimen_arms import (
    claim_components_from_object,
    match_claim_to_arms,
    normalize_source_arms,
)
from backend.pipeline.agentic.source_profile_cache import statement_hash

# Versione del prompt del profilo sorgente: incrementare quando cambia la
# logica di estrazione (section 1 del prompt sotto), per invalidare
# automaticamente le voci di cache legate alla versione precedente.
SOURCE_PROFILE_PROMPT_VERSION = "v2"


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
Riporta anche source_arms: un elenco di bracci di studio, ciascuno con
arm_name e interventions (solo i farmaci di QUEL braccio — non unire mai
farmaci di bracci comparatori diversi in un solo elenco). Esempio: uno studio
con un braccio sperimentale "amivantamab+lazertinib" e un braccio di
comparazione "osimertinib" produce due bracci separati, non uno unico con
tutti e tre i farmaci. Non includere "placebo" come farmaco: è un
comparatore inerte. Se la fonte descrive un solo regime senza comparatori,
riporta comunque un solo braccio. Lascia vuoto se non determinabile.

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
  "source_arms": [{"arm_name": "...", "interventions": ["farmaco1", "farmaco2"]}],
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
    # Bracci di studio strutturati (arm_name + interventions per braccio, mai
    # uniti fra loro) e confronto deterministico della claim contro ciascun
    # braccio — sostituisce l'estrazione piatta basata su token generici.
    source_arms: list[dict[str, Any]] = field(default_factory=list)
    claim_arm_match: str = "unknown"
    # Proiezione contestualizzata della claim (mai una modifica del ledger
    # originale): generata solo quando la fonte supporta la claim con
    # prerequisiti aggiuntivi noti (popolazione/linea/setting/prerequisiti),
    # per distinguere un prerequisito legittimo da una contraddizione.
    derived_verified_claim: str | None = None


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
    str, str, str, list[dict[str, Any]],
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
            normalize_source_arms(result.get("source_arms")),
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
    source_arms: list[dict[str, Any]] | None = None,
    claim_arm_match: str = "unknown",
    derived_verified_claim: str | None = None,
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
        requires_source_review=source_support_status in {"uncertain", "contradicted"},
        requires_clinical_review=applicability_status in {"indeterminate", "not_compatible"},
        source_line_category=source_line_category,
        source_setting_category=source_setting_category,
        source_prior_therapy_requirement=source_prior_therapy_requirement,
        source_arms=list(source_arms) if source_arms else [],
        claim_arm_match=claim_arm_match,
        derived_verified_claim=derived_verified_claim,
    )


def _derive_verified_claim(
    item: Any,
    population: str | None,
    line: str | None,
    setting: str | None,
    prerequisites: str | None,
    full_regimen: str | None = None,
) -> str | None:
    """Proiezione contestualizzata della claim quando la fonte la supporta
    solo insieme a prerequisiti aggiuntivi noti (es. AURA3/PMID 27959700:
    "EGFR L858R" da solo non basta — la fonte riguarda L858R con T790M dopo
    progressione a un precedente EGFR-TKI) o a un regime farmacologico più
    ampio di quello scritto nella claim (es. MARIPOSA-2: la claim cita solo
    amivantamab + carboplatin, ma il braccio della fonte include anche
    pemetrexed). Non modifica mai il ledger originale (claim/evidence_statement
    restano intatti altrove); è esclusivamente una proiezione aggiuntiva per
    l'oncologo. Restituisce ``None`` quando non c'è nulla di strutturato da
    aggiungere (nessuna contestualizzazione necessaria) — non tenta mai di
    dedurre alcunché dal solo testo libero della motivazione."""
    context_parts = [part for part in (population, line, setting, prerequisites) if part]
    if not context_parts and full_regimen is None:
        return None
    relation_text = (item.relation or "associazione clinica").strip().lower()
    object_text = full_regimen or item.object
    if context_parts:
        context_note = ", ".join(context_parts)
        return f"{item.subject} con {context_note} è associato a {relation_text} a {object_text}."
    return f"{item.subject} è associato a {relation_text} a {object_text} (regime completo dichiarato dalla fonte)."


def _matched_arm_regimen_text(item: Any, source_arms: list[dict[str, Any]]) -> str | None:
    """Restituisce il regime completo del braccio di cui la claim è un
    sottoinsieme proprio — usato per contestualizzare (non per respingere) un
    match "partial": la fonte sostiene una claim più specifica di quella
    scritta nel KG (es. MARIPOSA-2), non una combinazione da scartare."""
    claim_components = claim_components_from_object(item.object)
    for arm in source_arms:
        arm_set = set(arm["interventions"])
        if claim_components and claim_components < arm_set:
            return " + ".join(sorted(arm_set))
    return None


def _regimen_check_reason(
    item: Any, claim_arm_match: str, source_arms: list[dict[str, Any]],
) -> str | None:
    """Fail-closed sulla base del confronto deterministico per bracci
    (``claim_arm_match``), mai su un'estrazione testuale generica:

    - "exact": la claim coincide con un braccio — nessuna riserva.
    - "partial": la claim è un sottoinsieme proprio di un braccio noto — la
      fonte sostiene una claim più specifica di quella scritta nel KG.
      Non è un fallimento: viene gestito altrove come contestualizzazione
      (``supported_after_contextualization``), non come riserva sul supporto.
    - "unknown": nessun braccio noto per confrontare una claim a più
      farmaci — non verificabile, riserva sul supporto.
    - "no_match": nessuna sovrapposizione fra claim e bracci noti; qui non
      degradiamo a "contradicted" (riservato a una vera contraddizione
      accertata altrove) ma segnaliamo comunque la mancata corrispondenza.
    """
    claim_components = claim_components_from_object(item.object)
    if len(claim_components) < 2:
        return None  # non è una claim di regime combinato: nessun controllo necessario
    if claim_arm_match in ("exact", "partial"):
        return None
    arm_summary = "; ".join(
        f"{arm['arm_name']}: {', '.join(arm['interventions']) or 'nessun farmaco riconosciuto'}"
        for arm in source_arms
    ) or "nessun braccio riportato dalla fonte"
    if claim_arm_match == "unknown":
        return (
            "La claim descrive un regime a più farmaci, ma la fonte non ha riportato bracci di "
            "studio verificabili: il supporto documentale non può essere confermato senza riserva."
        )
    if claim_arm_match == "no_match":
        return (
            "Il regime della claim non trova corrispondenza in alcun braccio riportato dalla fonte "
            f"({arm_summary}): supporto documentale non confermabile su questa combinazione."
        )
    return None


def _documentary_support_status(raw_support_status: str, contextualized: bool) -> str:
    """Tassonomia documentale a quattro valori — sostituisce il precedente
    schema binario supported/unsupported, che etichettava come "non
    supportate" fonti (AURA3, ADAURA, MARIPOSA-2) che in realtà sostengono una
    claim più specifica di quella scritta nel KG:

    - ``supported_as_written``: la fonte sostiene la claim così come scritta,
      senza bisogno di prerequisiti o regimi aggiuntivi.
    - ``supported_after_contextualization``: la fonte sostiene la claim solo
      insieme a prerequisiti/regime aggiuntivi noti — vedi ``derived_verified_claim``.
    - ``uncertain``: dato insufficiente per decidere (nessuna contraddizione).
    - ``contradicted``: la fonte contraddice realmente la claim (mai per
      genericità della claim o per una combinazione parziale non confermata).
    """
    if raw_support_status == "unsupported":
        return "contradicted"
    if raw_support_status == "uncertain":
        return "uncertain"
    return "supported_after_contextualization" if contextualized else "supported_as_written"


def _finalize_verification(
    *,
    index: int,
    item: Any,
    support_status: str,
    support_reason: str,
    population: str | None,
    line: str | None,
    setting: str | None,
    prerequisites: str | None,
    line_category: str,
    setting_category: str,
    prior_requirement: str,
    source_arms: list[dict[str, Any]],
    case_context: dict[str, str],
    llm_applicability: tuple[str, str] | None,
) -> SourceVerification:
    """Costruisce il risultato finale a partire dal profilo della fonte
    (fase A, eventualmente da cache) e dal contesto paziente corrente (fase
    B, sempre ricalcolata). Con ``llm_applicability`` fornito (chiamata LLM
    fresca), l'applicabilità passa per ``validate_applicability`` (convalida
    del verdict del modello); senza (profilo da cache), passa per
    ``derive_applicability`` (nessun verdict LLM disponibile né necessario)."""
    claim_arm_match = match_claim_to_arms(claim_components_from_object(item.object), source_arms)
    full_regimen = None
    if support_status == "supported":
        if claim_arm_match == "partial":
            full_regimen = _matched_arm_regimen_text(item, source_arms)
        else:
            regimen_reason = _regimen_check_reason(item, claim_arm_match, source_arms)
            if regimen_reason:
                support_status = "uncertain"
                support_reason = regimen_reason

    categories = {
        "source_line_category": line_category,
        "source_setting_category": setting_category,
        "source_prior_therapy_requirement": prior_requirement,
    }
    if llm_applicability is not None:
        applicability_status, applicability_reason = validate_applicability(
            categories, case_context, llm_applicability[0], llm_applicability[1],
        )
    else:
        applicability_status, applicability_reason = derive_applicability(categories, case_context)

    derived_verified_claim = (
        _derive_verified_claim(item, population, line, setting, prerequisites, full_regimen=full_regimen)
        if support_status == "supported"
        else None
    )
    documentary_support_status = _documentary_support_status(
        support_status, derived_verified_claim is not None,
    )

    return _verification(
        index=index,
        source_support_status=documentary_support_status,
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
        source_arms=source_arms,
        claim_arm_match=claim_arm_match,
        derived_verified_claim=derived_verified_claim,
    )


def verify_evidence_items(
    items: list[Any],
    *,
    llm_client: Any | None = None,
    source_loader: Callable[[Iterable[int]], dict[int, dict[str, str]]] = fetch_pubmed_sources,
    case_context: dict[str, str] | None = None,
    metrics: dict[str, int] | None = None,
    profile_cache: Any | None = None,
    model_revision: str = "default",
) -> list[SourceVerification]:
    """Verifica in modalità fail-closed: dubbio o fonte assente richiedono revisione.

    ``unsupported`` è riservato ai casi in cui la fonte è disponibile e
    contraddice realmente la claim: nessuno dei controlli strutturali qui
    sotto ha letto un contenuto contraddittorio, quindi producono sempre
    ``uncertain`` quando falliscono, mai ``unsupported``.

    Se ``metrics`` è fornito, viene popolato in-place con contatori
    diagnostici (``cache_hits``, ``cache_misses``, ``verifier_batches``,
    ``failed_batches``, ``retry_items``, ``recovered_items``,
    ``permanently_failed_items``, ``source_profile_elapsed_ms``,
    ``applicability_elapsed_ms``) senza cambiare il tipo di ritorno della
    funzione.

    Se ``profile_cache`` è fornito (``SourceProfileCache``/
    ``InMemorySourceProfileCache``, vedi ``source_profile_cache.py``), il
    profilo della fonte (asse del supporto, indipendente dal paziente) viene
    letto/scritto da cache per PMID+hash dello statement+versione prompt+
    modello: un cambio di contesto paziente non causa mai una nuova chiamata
    LLM per un PMID già in cache. Senza ``profile_cache`` (default), il
    comportamento è invariato: nessuna cache, ogni chiamata è fresca.
    """
    verification_started = perf_counter()
    if not items:
        if metrics is not None:
            metrics.update(
                cache_hits=0,
                cache_misses=0,
                verifier_batches=0,
                failed_batches=0,
                retry_items=0,
                recovered_items=0,
                permanently_failed_items=0,
                source_profile_elapsed_ms=0,
                applicability_elapsed_ms=0,
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
    cached_profiles: dict[int, dict[str, Any]] = {}
    payload_pmid_by_index: dict[int, int] = {}
    payload_statement_hash_by_index: dict[int, str] = {}
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
        cached_profile = None
        if profile_cache is not None:
            cached_profile = profile_cache.get(
                pmid, statement_hash(item.evidence_statement, item.citation_text),
                SOURCE_PROFILE_PROMPT_VERSION, model_revision,
            )
        if cached_profile is not None:
            cached_profiles[index] = cached_profile
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
        payload_pmid_by_index[index] = pmid
        payload_statement_hash_by_index[index] = statement_hash(item.evidence_statement, item.citation_text)

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

    permanently_failed_items = retry_items - recovered_items
    source_profile_elapsed_ms = int((perf_counter() - verification_started) * 1000)

    results: list[SourceVerification] = []
    applicability_started = perf_counter()
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

        cached_profile = cached_profiles.get(index)
        if cached_profile is not None:
            results.append(_finalize_verification(
                index=index,
                item=items[index],
                support_status=cached_profile["support_status"],
                support_reason=cached_profile["support_reason"],
                population=cached_profile["population"],
                line=cached_profile["line"],
                setting=cached_profile["setting"],
                prerequisites=cached_profile["prerequisites"],
                line_category=cached_profile["line_category"],
                setting_category=cached_profile["setting_category"],
                prior_requirement=cached_profile["prior_requirement"],
                source_arms=cached_profile["source_arms"],
                case_context=case_context or {},
                llm_applicability=None,
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
            source_arms: list[dict[str, Any]] = []
        else:
            (
                support_status, support_reason,
                population, line, setting, prerequisites,
                applicability_status, applicability_reason,
                line_category, setting_category, prior_requirement,
                source_arms,
            ) = parsed
        if support_status not in {"supported", "unsupported", "uncertain"}:
            support_status = "uncertain"
        if applicability_status not in {"compatible", "indeterminate", "not_compatible"}:
            applicability_status = "indeterminate"

        if profile_cache is not None and parsed is not None:
            profile_cache.put(
                payload_pmid_by_index[index], payload_statement_hash_by_index[index],
                SOURCE_PROFILE_PROMPT_VERSION, model_revision,
                {
                    "support_status": support_status,
                    "support_reason": support_reason,
                    "population": population,
                    "line": line,
                    "setting": setting,
                    "prerequisites": prerequisites,
                    "line_category": line_category,
                    "setting_category": setting_category,
                    "prior_requirement": prior_requirement,
                    "source_arms": source_arms,
                },
            )

        results.append(_finalize_verification(
            index=index,
            item=items[index],
            support_status=support_status,
            support_reason=support_reason,
            population=population,
            line=line,
            setting=setting,
            prerequisites=prerequisites,
            line_category=line_category,
            setting_category=setting_category,
            prior_requirement=prior_requirement,
            source_arms=source_arms,
            case_context=case_context or {},
            llm_applicability=(applicability_status, applicability_reason),
        ))

    if metrics is not None:
        metrics.update(
            cache_hits=len(cached_profiles),
            cache_misses=len(payload_pmid_by_index),
            verifier_batches=batches_run,
            failed_batches=failed_batches,
            retry_items=retry_items,
            recovered_items=recovered_items,
            permanently_failed_items=permanently_failed_items,
            source_profile_elapsed_ms=source_profile_elapsed_ms,
            applicability_elapsed_ms=int((perf_counter() - applicability_started) * 1000),
        )
    return results
