"""Narrative Verifier — deterministico, senza LLM.

Riceve ``canonical_dossier``, ``narrator_input`` e ``narrative_output`` e decide
se la narrativa può essere mostrata. Non chiama modelli, non fa retrieval, non
interroga il KG né documenti esterni: le sole fonti sono i tre input.

Non giudica la **correttezza clinica**. Giudica la **fedeltà** della narrativa
rispetto a un dossier già deciso. È una distinzione deliberata: la correttezza
clinica non è verificabile deterministicamente, la fedeltà sì.

Sei famiglie di controllo, ognuna con il proprio reason code:

    §10  entity closure          NARRATIVE_UNAUTHORIZED_ENTITY
    §11  status preservation     NARRATIVE_STATUS_ESCALATION
    §12  polarity preservation   NARRATIVE_POLARITY_INVERSION · NARRATIVE_NEGATION_LOST
    §13  quote e provenance      NARRATIVE_UNAUTHORIZED_QUOTE · NARRATIVE_REJECTED_QUOTE_PROMOTED
    §14  recommendation          NARRATIVE_UNAUTHORIZED_RECOMMENDATION
    §15  omissioni critiche      NARRATIVE_CRITICAL_LIMITATION_OMITTED
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from ..dossier.builder import PRESENTABLE_AS_AUTHOR_CLAIM
from . import lexicon as lx
from .input_projection import NARRATIVE_CRITICAL_WARNINGS, allowed_entities

VERIFIER_VERSION = "narrative-verifier/1.0"

PASS = "PASS"
FAIL = "FAIL"

REASON_UNAUTHORIZED_ENTITY = "NARRATIVE_UNAUTHORIZED_ENTITY"
REASON_STATUS_ESCALATION = "NARRATIVE_STATUS_ESCALATION"
REASON_POLARITY_INVERSION = "NARRATIVE_POLARITY_INVERSION"
REASON_NEGATION_LOST = "NARRATIVE_NEGATION_LOST"
REASON_UNAUTHORIZED_QUOTE = "NARRATIVE_UNAUTHORIZED_QUOTE"
REASON_REJECTED_QUOTE_PROMOTED = "NARRATIVE_REJECTED_QUOTE_PROMOTED"
REASON_UNAUTHORIZED_RECOMMENDATION = "NARRATIVE_UNAUTHORIZED_RECOMMENDATION"
REASON_CRITICAL_OMISSION = "NARRATIVE_CRITICAL_LIMITATION_OMITTED"
REASON_UNKNOWN_CANDIDATE = "NARRATIVE_UNKNOWN_CANDIDATE_ID"
REASON_MISSING_CANDIDATE = "NARRATIVE_MISSING_CANDIDATE"

#: Identificatori documentali riconoscibili nel testo. Volutamente stretti:
#: cercano forme canoniche, non qualunque numero.
_IDENTIFIER_RE = re.compile(
    r"\b(?:PMID[:\s]?\d{4,9}|pmid:\d{4,9}|NCT\d{8}|10\.\d{4,9}/[^\s,;\)]+)", re.IGNORECASE)

#: Simboli in maiuscolo: geni (EGFR, KRAS, BRAF, TP53, FGFR1) e farmaci scritti
#: come nel dossier (PANITUMUMAB, NIVOLUMAB). Nessun limite superiore di
#: lunghezza: era 7 caratteri e lasciava passare PEMBROLIZUMAB.
_GENE_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")

#: Radici INN dei farmaci oncologici. Regola **morfologica**, non un elenco di
#: farmaci: un elenco sarebbe sempre incompleto e andrebbe mantenuto, mentre le
#: radici INN sono assegnate dall'OMS per classe. Cattura un nome inventato dal
#: modello anche quando è scritto in minuscolo, dove la regola sui simboli
#: maiuscoli non arriva.
_DRUG_STEM_RE = re.compile(
    r"\b\w{4,}(?:mab|nib|tinib|ciclib|parib|zomib|platin|rubicin|taxel|tecan|"
    r"mustine|fenib|degib|lisib|rafenib|tuzumab|ximab|umab|zumab|limus|sertib)\b",
    re.IGNORECASE)

#: Parole tutte-maiuscole che non sono geni e non vanno trattate come entità.
_GENE_STOPWORDS = frozenset({
    "MTB", "KG", "LLM", "ID", "PMID", "NCT", "DOI", "AND", "OR", "NOT", "THE",
    "DIRECT", "PARTIAL", "AMBIGUOUS", "CONTRADICTED", "DISCOVERED", "NO_MATCH",
    "SUPPORTED", "PRIMARY", "WARNING", "REJECTED", "DISCOVERY", "AUDIT",
    "QUOTE", "ABSTAIN", "GCA", "SU", "EB", "IT", "DNA", "RNA", "OK",
})


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return set(_norm(text).split())


def _mentions(text: str, entity: str) -> bool:
    """L'entità compare nel testo, confronto normalizzato."""
    needle = _norm(entity)
    return bool(needle) and needle in _norm(text)


def _authorized_token_pool(narrator_input: dict[str, Any], allowed: dict[str, set[str]]) -> set[str]:
    """Token che possono legittimamente comparire nella narrativa.

    Include le entità autorizzate e i valori del dossier: uno di questi token in
    un simbolo maiuscolo non è un'invenzione.
    """
    pool: set[str] = set()
    for group in allowed.values():
        for value in group:
            pool |= _tokens(value)
    pool |= _tokens(json.dumps(narrator_input, ensure_ascii=False))
    return pool


def _narrative_texts(narrative: dict[str, Any]) -> list[tuple[str, str]]:
    """(etichetta, testo) di ogni blocco narrativo."""
    blocks = [
        ("narrative_summary", narrative.get("narrative_summary") or ""),
        ("limitations_summary", narrative.get("limitations_summary") or ""),
        ("closing_note", narrative.get("closing_note") or ""),
    ]
    for entry in narrative.get("candidate_narratives") or []:
        blocks.append((f"candidate:{entry.get('candidate_id')}", entry.get("text") or ""))
    return blocks


def _full_text(narrative: dict[str, Any]) -> str:
    return "\n".join(text for _, text in _narrative_texts(narrative))


# ══════════════════════════════════════════════════════════ §10 entity closure

def _check_entities(narrative, narrator_input, allowed) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    pool = _authorized_token_pool(narrator_input, allowed)
    text = _full_text(narrative)

    for identifier in set(_IDENTIFIER_RE.findall(text)):
        if not any(_norm(identifier) in _norm(a) or _norm(a) in _norm(identifier)
                   for a in allowed["identifiers"]):
            violations.append({"kind": "identifier", "value": identifier})

    for symbol in set(_GENE_RE.findall(text)):
        if symbol in _GENE_STOPWORDS or symbol.lower() in pool:
            continue
        violations.append({"kind": "gene_or_symbol", "value": symbol})

    # Farmaci riconosciuti per radice INN, in qualunque grafia.
    for token in set(_DRUG_STEM_RE.findall(text)):
        if token.lower() in pool:
            continue
        violations.append({"kind": "drug", "value": token})

    return violations


def _check_candidate_ids(narrative, narrator_input) -> tuple[list[str], list[str]]:
    known = {c["candidate_id"] for c in narrator_input.get("candidates") or []}
    narrated = {e.get("candidate_id") for e in narrative.get("candidate_narratives") or []}
    return sorted(narrated - known), sorted(known - narrated)


# ═════════════════════════════════════════════════════ §11 status preservation

def _check_status(candidate, text) -> list[dict[str, Any]]:
    """Una candidate che non esprime supporto non può essere narrata come supportata."""
    if candidate.get("expresses_support"):
        return []
    hits = lx.support_claim_hits(text)
    if not hits:
        return []
    return [{"candidate_id": candidate["candidate_id"],
             "canonical_status": candidate["canonical_status"],
             "support_direction": candidate["support_direction"],
             "phrases": hits}]


# ═══════════════════════════════════════════════════ §12 polarity preservation

def _check_polarity(candidate, text) -> tuple[list[dict], list[dict]]:
    inversions, lost = [], []
    direction = candidate.get("support_direction")
    if direction in ("SOURCE_DOES_NOT_SUPPORT", "CONTRADICTED"):
        if lx.support_claim_hits(text):
            inversions.append({"candidate_id": candidate["candidate_id"],
                               "support_direction": direction,
                               "phrases": lx.support_claim_hits(text)})
        if not lx.has_negation_marker(text):
            lost.append({"candidate_id": candidate["candidate_id"],
                         "support_direction": direction,
                         "detail": "nessun marcatore di negazione nella narrativa"})
    return inversions, lost


# ═══════════════════════════════════════════════════════ §13 quote e provenance

def _check_quotes(narrative, canonical_dossier, allowed) -> tuple[list[dict], list[dict]]:
    """Le quote citate devono appartenere all'insieme validato.

    Vengono estratte le stringhe fra virgolette (tipografiche o dritte) di
    lunghezza significativa: una citazione breve non è una citazione.
    """
    unauthorized, promoted = [], []
    rejected = {
        (v.get("author_claim_quote") or "").strip()
        for entry in canonical_dossier.get("candidate_therapies") or []
        for v in entry.get("author_context") or []
        if v.get("presentation_state") not in PRESENTABLE_AS_AUTHOR_CLAIM
        and (v.get("author_claim_quote") or "").strip()
    }
    validated_norm = {_norm(q) for q in allowed["quotes"]}

    for label, text in _narrative_texts(narrative):
        for raw in re.findall(r"[\"“«]([^\"”»]{25,})[\"”»]", text):
            candidate_quote = raw.strip()
            norm = _norm(candidate_quote)
            if any(norm in v or v in norm for v in validated_norm if v):
                continue
            if any(_norm(r) and (norm in _norm(r) or _norm(r) in norm) for r in rejected):
                promoted.append({"block": label, "quote": candidate_quote[:160]})
            else:
                unauthorized.append({"block": label, "quote": candidate_quote[:160]})
    return unauthorized, promoted


# ═══════════════════════════════════════════════════════ §14 recommendation

def _check_recommendation(narrative) -> list[dict[str, Any]]:
    found = []
    for label, text in _narrative_texts(narrative):
        hits = lx.recommendation_hits(text)
        if hits:
            found.append({"block": label, "phrases": hits})
    return found


# ═══════════════════════════════════════════════════════ §15 omissioni critiche

def _check_omissions(candidate, text) -> list[dict[str, Any]]:
    """Solo i warning dichiarati NARRATIVE_CRITICAL. Gli altri sono tecnici."""
    omissions = []
    critical = set(candidate.get("critical_warnings") or [])

    if candidate.get("canonical_status") == "AMBIGUOUS" and not lx.has_uncertainty_marker(text):
        omissions.append({"candidate_id": candidate["candidate_id"],
                          "omitted": "AMBIGUITY_NOT_STATED"})
    if "NO_VALIDATED_ENRICHMENT_AVAILABLE" in critical and not lx.has_no_document_marker(text):
        omissions.append({"candidate_id": candidate["candidate_id"],
                          "omitted": "NO_VALIDATED_QUOTE_NOT_STATED"})
    if candidate.get("source_does_not_support") and not lx.has_negation_marker(text):
        omissions.append({"candidate_id": candidate["candidate_id"],
                          "omitted": "SOURCE_DOES_NOT_SUPPORT_NOT_STATED"})
    return omissions


# ══════════════════════════════════════════════════════════════════ verify

def verify_narrative(
    canonical_dossier: dict[str, Any],
    narrator_input: dict[str, Any],
    narrative_output: dict[str, Any] | None,
) -> dict[str, Any]:
    """``NarrativeVerificationResult``. Deterministico: nessun LLM, nessuna rete."""
    now = datetime.now(timezone.utc).isoformat()
    input_hash = (narrator_input or {}).get("narrator_input_hash", "")

    if not narrative_output:
        return {
            "status": FAIL, "reason_codes": ["NARRATIVE_ABSENT"],
            "candidate_results": [], "unauthorized_entities": [], "status_escalations": [],
            "polarity_violations": [], "unauthorized_quotes": [], "recommendation_language": [],
            "critical_omissions": [], "verified_at": now, "verifier_version": VERIFIER_VERSION,
            "lexicon_version": lx.LEXICON_VERSION,
            "input_hash": input_hash, "narrative_hash": "",
        }

    allowed = allowed_entities(narrator_input)
    reason_codes: list[str] = []

    unknown_ids, missing_ids = _check_candidate_ids(narrative_output, narrator_input)
    if unknown_ids:
        reason_codes.append(REASON_UNKNOWN_CANDIDATE)
    if missing_ids:
        reason_codes.append(REASON_MISSING_CANDIDATE)

    unauthorized_entities = _check_entities(narrative_output, narrator_input, allowed)
    if unauthorized_entities:
        reason_codes.append(REASON_UNAUTHORIZED_ENTITY)

    recommendation_language = _check_recommendation(narrative_output)
    if recommendation_language:
        reason_codes.append(REASON_UNAUTHORIZED_RECOMMENDATION)

    unauthorized_quotes, promoted_quotes = _check_quotes(
        narrative_output, canonical_dossier or {}, allowed)
    if unauthorized_quotes:
        reason_codes.append(REASON_UNAUTHORIZED_QUOTE)
    if promoted_quotes:
        reason_codes.append(REASON_REJECTED_QUOTE_PROMOTED)

    by_id = {c["candidate_id"]: c for c in narrator_input.get("candidates") or []}
    text_by_id: dict[str, str] = {}
    for entry in narrative_output.get("candidate_narratives") or []:
        cid = entry.get("candidate_id")
        text_by_id[cid] = f"{text_by_id.get(cid, '')}\n{entry.get('text') or ''}".strip()

    escalations, inversions, negations_lost, omissions = [], [], [], []
    candidate_results = []
    for cid, candidate in by_id.items():
        text = text_by_id.get(cid, "")
        c_esc = _check_status(candidate, text)
        c_inv, c_lost = _check_polarity(candidate, text)
        c_omit = _check_omissions(candidate, text)
        escalations += c_esc
        inversions += c_inv
        negations_lost += c_lost
        omissions += c_omit
        candidate_results.append({
            "candidate_id": cid,
            "canonical_status": candidate["canonical_status"],
            "support_direction": candidate["support_direction"],
            "narrated": bool(text),
            "status_escalation": bool(c_esc),
            "polarity_inversion": bool(c_inv),
            "negation_lost": bool(c_lost),
            "critical_omissions": [o["omitted"] for o in c_omit],
        })

    if escalations:
        reason_codes.append(REASON_STATUS_ESCALATION)
    if inversions:
        reason_codes.append(REASON_POLARITY_INVERSION)
    if negations_lost:
        reason_codes.append(REASON_NEGATION_LOST)
    if omissions:
        reason_codes.append(REASON_CRITICAL_OMISSION)

    return {
        "status": FAIL if reason_codes else PASS,
        "reason_codes": sorted(set(reason_codes)),
        "candidate_results": candidate_results,
        "unknown_candidate_ids": unknown_ids,
        "missing_candidate_ids": missing_ids,
        "unauthorized_entities": unauthorized_entities,
        "status_escalations": escalations,
        "polarity_violations": inversions + negations_lost,
        "unauthorized_quotes": unauthorized_quotes + promoted_quotes,
        "recommendation_language": recommendation_language,
        "critical_omissions": omissions,
        "verified_at": now,
        "verifier_version": VERIFIER_VERSION,
        "lexicon_version": lx.LEXICON_VERSION,
        "input_hash": input_hash,
        "narrative_hash": narrative_output.get("narrative_hash") or "",
    }


def result_fingerprint(result: dict[str, Any]) -> str:
    """Impronta deterministica dell'esito, esclusi i campi temporali."""
    body = {k: v for k, v in result.items() if k != "verified_at"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
