"""Narrative Verifier — deterministico, senza LLM.

Riceve ``canonical_dossier``, ``narrator_input`` e ``narrative_output`` e decide
se la narrativa può essere mostrata. Non chiama modelli, non fa retrieval, non
interroga il KG né documenti esterni: le sole fonti sono i tre input.

Non giudica la **correttezza clinica** né dimostra equivalenza semantica generale.
Verifica vincoli espliciti di identità, citazione, conteggio e scope rispetto
a un dossier già deciso; la prosa libera resta soggetta a controlli limitati.

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
from .coverage import candidate_text, coverage_errors, observation_text
from .input_projection import NARRATIVE_CRITICAL_WARNINGS, allowed_entities, _summary_facts

VERIFIER_VERSION = "narrative-verifier/3.3"


def _check_generated_contract(narrative: dict, source: dict) -> list[str]:
    """Structural binding and number closure for generated dossier prose.

    These are bounded deterministic checks, not a semantic entailment proof.
    Legacy callback outputs keep their historical validation contract.
    """
    if 'dossier_narration_contract' not in narrative:
        return []
    from .input_projection import narrator_input_hash
    from .output_contract import METADATA_KEYS, body_hash, valid_body
    from .prompt import REQUIRED_KEYS

    errors = []
    contract = narrative.get('dossier_narration_contract')
    expected_hash = narrator_input_hash(source)
    if (not isinstance(contract, dict)
            or set(contract) != {'version', 'input_hash'}
            or contract.get('version') not in {'dossier-narration/1.0', 'dossier-narration/1.1', 'dossier-narration/1.2', 'dossier-narration/1.3', 'dossier-narration/1.4'}
            or contract.get('input_hash') != expected_hash
            or source.get('narrator_input_hash') != expected_hash
            or narrative.get('narrator_input_hash') != expected_hash):
        errors.append('NARRATIVE_INPUT_BINDING_MISMATCH')
    body = {key: narrative.get(key) for key in REQUIRED_KEYS}
    if not valid_body(body) or set(narrative) - set(REQUIRED_KEYS) - METADATA_KEYS:
        errors.append('NARRATIVE_SHAPE_INVALID')
        return errors
    if narrative.get('narrative_hash') != body_hash(narrative):
        errors.append('NARRATIVE_HASH_MISMATCH')
    if (isinstance(contract, dict) and contract.get('version') in {'dossier-narration/1.1', 'dossier-narration/1.2', 'dossier-narration/1.3', 'dossier-narration/1.4'}
            and source.get('case_overview') and narrative.get('narrative_summary') != source['case_overview']):
        errors.append('NARRATIVE_CASE_OVERVIEW_CHANGED')
    if isinstance(contract, dict) and contract.get('version') in {'dossier-narration/1.2', 'dossier-narration/1.3', 'dossier-narration/1.4'}:
        expected_sources = {candidate['candidate_id']: candidate.get('source_cards') or []
                            for candidate in source.get('candidates') or []}
        if narrative.get('canonical_sources') != expected_sources:
            errors.append('NARRATIVE_SOURCE_BLOCK_MISMATCH')
    if isinstance(contract, dict) and contract.get('version') in {'dossier-narration/1.3', 'dossier-narration/1.4'}:
        expected_observations = {candidate['candidate_id']: candidate.get('narration_observations') or []
                                 for candidate in source.get('candidates') or []}
        if narrative.get('canonical_observations') != expected_observations:
            errors.append('NARRATIVE_OBSERVATION_BLOCK_MISMATCH')
        entries = {entry['candidate_id']: entry for entry in body['candidate_narratives']}
        for candidate in source.get('candidates') or []:
            entry = entries.get(candidate['candidate_id'], {})
            errors.extend(coverage_errors(candidate, entry))
            observations = {o['observation_id']: o for o in candidate.get('narration_observations') or []}
            for explanation in entry.get('observation_narratives') or []:
                if contract['version'] == 'dossier-narration/1.4' and not str(explanation.get('case_relevance') or '').strip():
                    errors.append('NARRATIVE_CASE_LINK_OMITTED')
                observation = observations.get(explanation['observation_id'])
                if observation is None:
                    continue
                scoped = {'case': source.get('case'), 'candidates': [{
                    'candidate_id': candidate['candidate_id'],
                    'narration_observations': [observation],
                    'source_cards': [{**(observation.get('source') or {}),
                                      'validated_quote': observation.get('quotation')}]}]}
                prose = {'candidate_narratives': [{'candidate_id': candidate['candidate_id'],
                                                   'text': observation_text(explanation)}]}
                quotes, _ = _check_quotes(prose, {}, allowed_entities(scoped), scoped)
                references, types = _check_source_refs(prose, scoped)
                identifiers = [violation for violation in _check_entities(prose, scoped, allowed_entities(scoped))
                               if violation.get('kind') == 'identifier']
                if quotes or references or types or identifiers:
                    errors.append('NARRATIVE_OBSERVATION_SOURCE_MISMATCH')
                disease_check = ((observation.get('checks') or {}).get('correspondence') or {}).get('fields') or {}
                if disease_check.get('disease') == 'NOT_CONFIRMED':
                    prose_text = observation_text(explanation)
                    for match in re.finditer(r'\bla\s+malattia\s+non\s+[èe]\s+stata\s+confermata\b', prose_text, re.IGNORECASE):
                        start = max(prose_text.rfind(mark, 0, match.start()) for mark in '.!?;') + 1
                        if not re.search(r'\bcorrispondenza\b', prose_text[start:match.start()], re.IGNORECASE):
                            errors.append('NARRATIVE_DISEASE_CHECK_MISSTATED')
        if contract['version'] == 'dossier-narration/1.4' and source.get('presentation_scope_note'):
            if narrative.get('limitations_summary') != source['presentation_scope_note']:
                errors.append('NARRATIVE_CLINICAL_SCOPE_OMITTED')
    expected = [c['candidate_id'] for c in source.get('candidates') or []]
    if [c['candidate_id'] for c in body['candidate_narratives']] != expected:
        errors.append('NARRATIVE_CANDIDATE_ORDER_MISMATCH')
    numbers = re.compile(r'(?<![\w])\d+(?:[.,]\d+)*(?:\s*%)?(?![\w])')
    # Identifiers, hashes and operational metadata do not license quantities.
    def factual_values(value):
        if isinstance(value, dict):
            return {key: factual_values(item) for key, item in value.items()
                    if not any(marker in key for marker in ('hash', 'version', 'timestamp', '_id'))
                    and key not in {'selected_paper_ids', 'source_refs'}}
        if isinstance(value, list):
            return [factual_values(item) for item in value]
        return value

    def quantities(value):
        return {re.sub(r'\s+', '', token) for token in numbers.findall(value)}

    globals_pool = quantities(json.dumps(factual_values(source), ensure_ascii=False))
    globals_pool.update(str(value) for value in _summary_facts(source.get('candidates') or []).values()
                        if type(value) is int)
    by_id = {c['candidate_id']: c for c in source.get('candidates') or []}
    references = _authorized_source_refs(source)
    for label, text in _narrative_texts(narrative):
        if label.startswith('candidate:'):
            candidate = by_id.get(label.removeprefix('candidate:'), {})
            if isinstance(contract, dict) and contract.get('version') == 'dossier-narration/1.1':
                for card in candidate.get('source_cards') or []:
                    identity = card.get('public_source_identity') or card.get('paper_id')
                    if identity and _norm(str(identity)) not in _norm(text):
                        errors.append('NARRATIVE_SOURCE_IDENTIFICATION_OMITTED')
                    if card.get('title') and card['title'] not in text:
                        errors.append('NARRATIVE_SOURCE_TITLE_OMITTED')
                    if card.get('validated_quote') and card['validated_quote'] not in text:
                        errors.append('NARRATIVE_SOURCE_QUOTE_OMITTED')
            if (candidate.get('documentary_contract_version')
                    and not candidate.get('documentary_findings')
                    and not candidate.get('documentary_attempts')
                    and re.search(r'\bnon\s+sono\s+stati\s+(?:reperiti|trovati|recuperati)\s+'
                                  r'(?:alcuni\s+)?documenti\b', text, re.IGNORECASE)):
                errors.append('NARRATIVE_UNSUPPORTED_RETRIEVAL_CLAIM')
            pool = quantities(json.dumps(factual_values({'case': source.get('case'),
                                                        'candidate': candidate}), ensure_ascii=False))
        else:
            pool = globals_pool
        # Source references are checked independently; their digits are not quantities.
        cleaned = _IDENTIFIER_RE.sub('', text)
        refs = (references.get(label.removeprefix('candidate:'), set())
                if label.startswith('candidate:')
                else set().union(*references.values()) if references else set())
        case_id = (source.get('case') or {}).get('case_id')
        if isinstance(case_id, str) and case_id:
            refs = refs | {case_id}
        for ref in sorted(refs | set(by_id), key=len, reverse=True):
            cleaned = re.sub(r'(?<!\w)' + re.escape(ref) + r'(?!\w)', '', cleaned,
                             flags=re.IGNORECASE)
        if quantities(cleaned) - pool:
            errors.append('NARRATIVE_UNAUTHORIZED_NUMBER')
    if isinstance(contract, dict) and contract.get('version') in {'dossier-narration/1.3', 'dossier-narration/1.4'}:
        for entry in body['candidate_narratives']:
            candidate = by_id.get(entry['candidate_id'], {})
            observations = {o['observation_id']: o for o in candidate.get('narration_observations') or []}
            for explanation in entry.get('observation_narratives') or []:
                observation = observations.get(explanation['observation_id'])
                if observation is None:
                    continue
                scoped_pool = quantities(json.dumps(factual_values({
                    'case': source.get('case'), 'observation': observation}), ensure_ascii=False))
                cleaned = _IDENTIFIER_RE.sub('', observation_text(explanation))
                for ref in sorted(_authorized_source_refs({'candidates': [{
                    'candidate_id': entry['candidate_id'],
                    'source_cards': [observation.get('source') or {}]}]}).get(entry['candidate_id'], set()), key=len, reverse=True):
                    cleaned = re.sub(r'(?<!\w)' + re.escape(ref) + r'(?!\w)', '', cleaned, flags=re.IGNORECASE)
                if quantities(cleaned) - scoped_pool:
                    errors.append('NARRATIVE_OBSERVATION_NUMBER_MISMATCH')
    return sorted(set(errors))

PASS = "PASS"
FAIL = "FAIL"

REASON_UNAUTHORIZED_ENTITY = "NARRATIVE_UNAUTHORIZED_ENTITY"
REASON_STATUS_ESCALATION = "NARRATIVE_STATUS_ESCALATION"
REASON_SUPPORT_LEVEL_ESCALATION = "NARRATIVE_SUPPORT_LEVEL_ESCALATION"
REASON_POLARITY_INVERSION = "NARRATIVE_POLARITY_INVERSION"
REASON_NEGATION_LOST = "NARRATIVE_NEGATION_LOST"
REASON_UNAUTHORIZED_QUOTE = "NARRATIVE_UNAUTHORIZED_QUOTE"
REASON_REJECTED_QUOTE_PROMOTED = "NARRATIVE_REJECTED_QUOTE_PROMOTED"
REASON_UNAUTHORIZED_RECOMMENDATION = "NARRATIVE_UNAUTHORIZED_RECOMMENDATION"
REASON_CRITICAL_OMISSION = "NARRATIVE_CRITICAL_LIMITATION_OMITTED"
REASON_UNKNOWN_CANDIDATE = "NARRATIVE_UNKNOWN_CANDIDATE_ID"
REASON_MISSING_CANDIDATE = "NARRATIVE_MISSING_CANDIDATE"
REASON_TRIAL_EFFICACY_ESCALATION = "NARRATIVE_TRIAL_EFFICACY_ESCALATION"
REASON_TRIAL_ELIGIBILITY_ESCALATION = "NARRATIVE_TRIAL_ELIGIBILITY_ESCALATION"
REASON_KG_DOCUMENTARY_ESCALATION = "NARRATIVE_KG_ONLY_DOCUMENTARY_ESCALATION"
REASON_KG_STATUS_MISMATCH = "NARRATIVE_KG_ONLY_STATUS_MISMATCH"
REASON_UNAUTHORIZED_SOURCE_REF = "NARRATIVE_UNAUTHORIZED_SOURCE_REF"
REASON_SOURCE_REF_TYPE_MISMATCH = "NARRATIVE_SOURCE_REF_TYPE_MISMATCH"
REASON_DUPLICATE_CANDIDATE = "NARRATIVE_DUPLICATE_CANDIDATE_ID"
REASON_SUMMARY_STATUS_CLAIM = "NARRATIVE_SUMMARY_STATUS_CLAIM"

#: Identificatori documentali riconoscibili nel testo. Volutamente stretti:
#: cercano forme canoniche, non qualunque numero.
_IDENTIFIER_RE = re.compile(
    r"\b(?:PMID[:\s]?\d+|NCT\d+|10\.\d{4,9}/[^\s,;\)]+)(?!\w)", re.IGNORECASE)

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
        blocks.append((f"candidate:{entry.get('candidate_id')}", candidate_text(entry)))
    return blocks


def _full_text(narrative: dict[str, Any]) -> str:
    return "\n".join(text for _, text in _narrative_texts(narrative))


# ══════════════════════════════════════════════════════════ §10 entity closure

def _check_entities(narrative, narrator_input, allowed) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    global_pool = _authorized_token_pool(narrator_input, allowed)
    case_pool = _tokens(json.dumps(narrator_input.get("case") or {}, ensure_ascii=False))
    candidates = {
        str(candidate.get("candidate_id")): candidate
        for candidate in narrator_input.get("candidates") or []
        if isinstance(candidate, dict) and candidate.get("candidate_id")
    }

    refs_by_candidate = _authorized_source_refs(narrator_input)
    def identity(value):
        return re.sub(r"^pmid[:\s]?", "pmid:", str(value).casefold())
    for label, block in _narrative_texts(narrative):
        refs = (refs_by_candidate.get(label.removeprefix("candidate:"), set())
                if label.startswith("candidate:") else allowed["identifiers"])
        identities = {identity(ref) for ref in refs}
        for identifier in set(_IDENTIFIER_RE.findall(block)):
            if identity(identifier) not in identities:
                violations.append({"kind": "identifier", "value": identifier, "block": label})

        # Candidate prose gets case-wide entities plus this candidate's facts.
        # A candidate cannot borrow another candidate's projected entities.
        if label.startswith("candidate:"):
            candidate = candidates.get(label.removeprefix("candidate:"), {})
            pool = case_pool | _tokens(json.dumps(candidate, ensure_ascii=False))
        else:
            pool = global_pool
        for symbol in set(_GENE_RE.findall(block)):
            if symbol in _GENE_STOPWORDS or symbol.lower() in pool:
                continue
            violations.append({"kind": "gene_or_symbol", "value": symbol, "block": label})

        # Farmaci riconosciuti per radice INN, in qualunque grafia.
        for token in set(_DRUG_STEM_RE.findall(block)):
            if token.lower() in pool:
                continue
            violations.append({"kind": "drug", "value": token, "block": label})

    return violations


def _check_candidate_ids(narrative, narrator_input) -> tuple[list[str], list[str], list[str]]:
    known = {c["candidate_id"] for c in narrator_input.get("candidates") or []}
    ids = [e.get("candidate_id") for e in narrative.get("candidate_narratives") or []]
    narrated = set(ids)
    duplicates = sorted({candidate_id for candidate_id in ids if ids.count(candidate_id) > 1})
    return sorted(narrated - known), sorted(known - narrated), duplicates


# ═════════════════════════════════════════════════════ §11 status preservation

def _check_status(candidate, text) -> list[dict[str, Any]]:
    """Una candidate che non esprime supporto non può essere narrata come supportata."""
    status_text = text
    authorized_quote_fragments: list[str] = []
    for quote in candidate.get("validated_quotes") or []:
        if isinstance(quote, dict) and isinstance(quote.get("quote"), str):
            authorized_quote = quote["quote"]
            status_text = status_text.replace(authorized_quote, " ")
            # The quote checker authorizes faithful excerpts too. Remove a
            # quoted excerpt when it is a contiguous fragment of the
            # validated quote, otherwise its source wording can be mistaken
            # for generated status prose (e.g. "are associated with").
            for match in re.finditer(r'[\"“](.+?)[\"”]', status_text, flags=re.DOTALL):
                fragment = match.group(1).strip()
                if len(fragment) >= 20 and fragment in authorized_quote:
                    authorized_quote_fragments.append(match.group(0))
    for fragment in authorized_quote_fragments:
        status_text = status_text.replace(fragment, " ")
    support = candidate.get("candidate_support") or {}
    support_result = support.get("result")
    if candidate.get("expresses_support") and support_result in (None, "STRONG_SUPPORT", "FULL_SUPPORT"):
        return []
    if candidate.get("branch") == "KG_ONLY":
        # A KG-only explanation must be able to state the absence of documentary
        # support.  The generic support lexicon otherwise mistakes the phrase
        # "non è supportata da evidenze documentali" for a positive claim.
        status_text = re.sub(
            r"\bnon\s+(?:è|sono)\s+supportat[oaie]\s+da\s+"
            r"(?:documenti|documentazione|evidenz[ae]\s+documental[ei])\b",
            lambda match: match.group(0) if lx.ends_in_local_negation(status_text[:match.start()]) else " ",
            status_text, flags=re.IGNORECASE,
        )
    hits = lx.support_claim_hits(status_text)
    if (
        support_result == "PARTIAL_SUPPORT"
        and re.search(
            r"\b(?:but|however|although|tuttavia|ma)\b.{0,180}"
            r"\b(?:not\s+confirmed|non\s+(?:è\s+)?confermat[oa])\b",
            status_text,
            re.IGNORECASE | re.DOTALL,
        )
    ):
        # A partial observation may truthfully say what the document supports
        # when the same sentence preserves the explicit missing-confirmation
        # caveat. Full-support wording remains covered by the level check.
        hits = [
            hit for hit in hits
            if re.search(r"\b(?:strongly|firmly|clearly|fully|completely|"
                         r"fortemente|chiaramente|pienamente|completamente)\b",
                         hit, re.IGNORECASE)
        ]
    if support_result in {"PARTIAL_SUPPORT", "CONTEXT_ONLY", "CONTRADICTORY", "UNVERIFIABLE", "INSUFFICIENT_INFORMATION"}:
        exact_relation = re.search(r"\b(?:is|are)\s+associated\s+with\b", status_text, re.IGNORECASE)
        if exact_relation:
            hits.append(exact_relation.group(0))
    if not hits:
        return []
    return [{"candidate_id": candidate["candidate_id"],
             "canonical_status": candidate["canonical_status"],
             "support_direction": candidate["support_direction"],
             "candidate_support": support_result,
             "phrases": hits}]


def _check_support_level(candidate, text) -> list[dict[str, Any]]:
    """Impedisce di narrare come piena una relazione non autorizzata."""
    direct = candidate.get("candidate_support") or {}
    levels = set()
    if isinstance(direct, dict) and isinstance(direct.get("result"), str):
        levels.add(direct["result"])
    for check in candidate.get("candidate_support_checks") or []:
        support = check.get("candidate_support") or {}
        if isinstance(support, dict) and isinstance(support.get("result"), str):
            levels.add(support["result"])

    restricted = bool(levels & {"PARTIAL_SUPPORT", "CONTEXT_ONLY", "CONTRADICTORY", "UNVERIFIABLE", "INSUFFICIENT_INFORMATION"})
    restricted = restricted or candidate.get("canonical_status") in {"PARTIAL", "AMBIGUOUS"}
    if not restricted:
        return []

    hits = lx.support_level_escalation_hits(text)
    fields = []
    if isinstance(direct, dict):
        fields = direct.get("fields") or []
    uncertain_biomarker = "BIOMARKER_MATCH_UNCERTAIN" in (candidate.get("warnings") or [])
    if uncertain_biomarker and lx.support_claim_hits(text):
        hits += lx.support_claim_hits(text)
    if not hits:
        return []
    return [{
        "candidate_id": candidate["candidate_id"],
        "candidate_support": sorted(levels) or None,
        "canonical_status": candidate.get("canonical_status"),
        "fields": fields,
        "phrases": hits,
    }]


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

def _check_quotes(narrative, canonical_dossier, allowed, narrator_input=None) -> tuple[list[dict], list[dict]]:
    """Le quote complete devono coincidere letteralmente con quelle dello scope.

    Vengono estratte le stringhe fra virgolette (tipografiche o dritte) di
    lunghezza significativa: una citazione breve non è una citazione.
    """
    unauthorized, promoted = [], []
    rejected = {
        (quote.get("quote") or "").strip()
        for entry in canonical_dossier.get("paper_evidence") or []
        for quote in entry.get("rejected_quotes") or []
        if (quote.get("quote") or "").strip()
    }
    # Compatibility fallback for dossiers produced before rejected_quotes was
    # promoted to the canonical paper projection.
    rejected.update({
        (v.get("author_claim_quote") or "").strip()
        for entry in canonical_dossier.get("candidate_therapies") or []
        for v in entry.get("author_context") or []
        if v.get("presentation_state") not in PRESENTABLE_AS_AUTHOR_CLAIM
        and (v.get("author_claim_quote") or "").strip()
    })
    by_candidate = {
        str(c.get("candidate_id")): {q["quote"] for q in c.get("validated_quotes") or []
                                    if isinstance(q.get("quote"), str)}
        for c in (narrator_input or {}).get("candidates") or []
    }
    for candidate in (narrator_input or {}).get('candidates') or []:
        quotes = by_candidate[str(candidate.get('candidate_id'))]
        quotes.update(card['validated_quote'] for card in candidate.get('source_cards') or []
                      if isinstance(card.get('validated_quote'), str))
        quotes.update(finding['quotation'] for finding in candidate.get('documentary_findings') or []
                      if finding.get('disposition') == 'RETAINED_RECORD'
                      and isinstance(finding.get('quotation'), str))

    for label, text in _narrative_texts(narrative):
        for raw in re.findall(r"[\"“«]([^\"”»]{25,})[\"”»]", text):
            candidate_quote = raw
            norm = _norm(candidate_quote)
            valid = (by_candidate.get(label.removeprefix("candidate:"), set())
                     if label.startswith("candidate:") else allowed["quotes"])
            scoped = [c for c in (narrator_input or {}).get('candidates') or []
                      if not label.startswith('candidate:') or c.get('candidate_id') == label.removeprefix('candidate:')]
            titles = {card.get('title') for c in scoped for card in c.get('source_cards') or [] if card.get('title')}
            if candidate_quote in titles:
                continue
            if candidate_quote in valid:
                continue
            if any(_norm(r) and (norm in _norm(r) or _norm(r) in norm) for r in rejected):
                promoted.append({"block": label, "quote": candidate_quote[:160]})
            else:
                unauthorized.append({"block": label, "quote": candidate_quote[:160]})
    return unauthorized, promoted


def _authorized_source_refs(narrator_input: dict[str, Any]) -> dict[str, set[str]]:
    """Collect source identifiers per candidate from the canonical projection."""
    refs_by_candidate: dict[str, set[str]] = {}
    for candidate in narrator_input.get("candidates") or []:
        refs: set[str] = set()
        cid = str(candidate.get("candidate_id") or "")
        refs.update(str(v) for v in candidate.get("selected_paper_ids") or [] if v)
        for card in candidate.get('source_cards') or []:
            for key in ('public_source_identity', 'document_id', 'paper_id', 'source_unit_id'):
                if card.get(key):
                    refs.add(str(card[key]))
        for quote in candidate.get("validated_quotes") or []:
            for key in ("paper_id", "source_unit_id"):
                if quote.get(key):
                    refs.add(str(quote[key]))
        for finding in candidate.get('documentary_findings') or []:
            source = finding.get('source') or {}
            for key in ('public_source_identity', 'document_id', 'paper_id', 'source_unit_id'):
                if source.get(key):
                    refs.add(str(source[key]))
        trial = candidate.get("trial_context") or {}
        if trial.get("nct_id"):
            refs.add(str(trial["nct_id"]))
        kg = candidate.get("kg_context") or {}
        provenance = kg.get("graph_provenance") or {}
        for key in ("edge_ids", "node_ids"):
            refs.update(str(v) for v in provenance.get(key) or [] if v)
        refs_by_candidate[cid] = refs
    return refs_by_candidate


def _check_source_refs(narrative, narrator_input) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject provenance claims that are not present in the dossier projection."""
    authorized_by_candidate = _authorized_source_refs(narrator_input)
    violations: list[dict[str, Any]] = []
    type_violations: list[dict[str, Any]] = []
    branch_by_id = {c.get("candidate_id"): c.get("branch") for c in narrator_input.get("candidates") or []}
    allowed_types = {"PAPER": "documentary", "TRIAL": "trial_context", "KG_ONLY": "kg_provenance"}
    for entry in narrative.get("candidate_narratives") or []:
        cid = entry.get("candidate_id")
        refs = list(entry.get("source_refs") or [])
        refs.extend(
            claim.get("source_ref")
            for claim in entry.get("claims") or []
            if isinstance(claim, dict) and claim.get("source_ref")
        )
        for ref in refs:
            if ref not in authorized_by_candidate.get(str(cid), set()):
                violations.append({"candidate_id": cid, "source_ref": ref})
        expected_type = allowed_types.get(branch_by_id.get(cid))
        if expected_type:
            for claim in entry.get("claims") or []:
                if isinstance(claim, dict) and claim.get("claim_type") != expected_type:
                    type_violations.append({"candidate_id": cid, "claim_type": claim.get("claim_type"),
                                            "expected": expected_type})
    return violations, type_violations


# ═══════════════════════════════════════════════════════ §14 recommendation

def _check_recommendation(narrative) -> list[dict[str, Any]]:
    found = []
    for label, text in _narrative_texts(narrative):
        hits = lx.recommendation_hits(text)
        if hits:
            found.append({"block": label, "phrases": hits})
    return found


def _check_summary_status_claim(narrative) -> list[dict[str, Any]]:
    summary = narrative.get("narrative_summary") or ""
    hits = lx.summary_status_claim_hits(summary)
    return [{"block": "narrative_summary", "phrases": hits}] if hits else []


def _clinical_benefit_is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 90):start]
    after = text[end:min(len(text), end + 90)]
    negated_claim = r"\b(?:non|not)\b[^.!?;]{0,50}\b(?:dimostrat\w*|confermat\w*|prov\w*|shown|established|demonstrated)\b"
    return bool(
        re.search(r"\bno\s+(?:(?:evidence\s+(?:of|for)|indication\s+of)\s+)?$",
                  before, re.IGNORECASE)
        or re.search(negated_claim + r"[^.!?;]{0,20}$", before, re.IGNORECASE)
        or re.search(negated_claim, after, re.IGNORECASE)
    )


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
    if candidate.get("contradiction_present") and not re.search(
        r"\b(?:contradict\w*|conflict\w*|discordant|inconsistent|mixed\s+evidence|"
        r"contraddittor\w*|contrastant\w*|evidenze\s+discordanti)\b",
        text or "", re.IGNORECASE,
    ):
        omissions.append({"candidate_id": candidate["candidate_id"],
                          "omitted": "CONTRADICTION_NOT_STATED"})
    normalized_text = lx.normalize(text or "").casefold()
    for limitation in candidate.get("required_limitations") or []:
        if not isinstance(limitation, dict):
            continue
        required_text = limitation.get("text")
        if not isinstance(required_text, str) or not required_text.strip():
            continue
        if lx.normalize(required_text).casefold() not in normalized_text:
            omissions.append({
                "candidate_id": candidate["candidate_id"],
                "omitted": "PARTIAL_SUPPORT_LIMITATION_NOT_STATED",
                "evidence_id": limitation.get("evidence_id"),
                "paper_id": limitation.get("paper_id"),
                "source_unit_id": limitation.get("source_unit_id"),
                "required_text": required_text,
            })
        if re.search(r"\b(?:preclinical|pre-clinical|in\s+vitro|cell\s+lines?|"
                     r"animal\s+models?|xenografts?)\b", required_text, re.IGNORECASE):
            clinical_claims = re.compile(
                r"\b(?:clinical\s+benefit|clinical\s+efficacy|benefit\s+in\s+patients|"
                r"effective\s+in\s+patients|patients?\s+(?:benefit|respond)|"
                r"beneficio\s+clinico|efficacia\s+clinica|efficace\s+nei\s+pazienti|"
                r"risposta\s+clinica)\b", re.IGNORECASE,
            )
            for match in clinical_claims.finditer(text or ""):
                if (not lx.ends_in_local_negation((text or "")[:match.start()])
                        and not _clinical_benefit_is_negated(text or "", match.start(), match.end())):
                    omissions.append({
                        "candidate_id": candidate["candidate_id"],
                        "omitted": "PRECLINICAL_SCOPE_CLINICAL_BENEFIT_ESCALATION",
                        "evidence_id": limitation.get("evidence_id"),
                        "paper_id": limitation.get("paper_id"),
                        "source_unit_id": limitation.get("source_unit_id"),
                        "required_text": required_text,
                        "observed_claim": match.group(0),
                    })
    return omissions


def _check_branch_semantics(candidate: dict[str, Any], text: str,
                            summary_facts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Prevent branch-specific context from being promoted in prose.

    These checks are deliberately lexical and deterministic.  They protect the
    semantic boundary already established by the structured dossier; they do
    not infer clinical truth or recalculate support.
    """
    branch = candidate.get("branch")
    lowered = (text or "").lower()
    violations: list[dict[str, Any]] = []
    if branch == "TRIAL":
        trial = candidate.get("trial_context") or {}
        if trial.get("evidence_interpretation") == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE":
            # Association-only trial prose uses a positive grammar. Unknown
            # formulations abstain instead of being licensed by the absence
            # of a few known escalation words.
            objects = [str(item).strip().casefold() for item in (
                *(trial.get("interventions") or []), *(trial.get("conditions") or []),
                trial.get("nct_id"), "an intervention", "a biomarker", "a condition",
            ) if item]
            object_pattern = "|".join(re.escape(item) for item in objects)
            allowed = [
                r"(?:the|this|a)?\s*trial\s+(?:exists|is\s+(?:listed|registered|available))",
                r"(?:the|this)?\s*trial\s+(?:is\s+)?associated\s+with\s+the\s+case",
                r"(?:the|this)?\s*trial\s+is\s+contextual,?\s+not\s+efficacy\s+evidence",
                r"trial\s+associat[oa]",
                r"la\s+relazione\s+resta\s+descrittiva",
                r"l['’]associazione\s+a\s+trial\s+non\s+costituisce\s+prova\s+di\s+efficacia",
                r"(?:il\s+dossier|il\s+sistema)\s+non\s+formula\s+raccomandazioni\s+cliniche",
                r"il\s+dossier\s+è\s+sperimentale",
                r"il\s+dossier\s+contiene\s+(?:[a-z0-9]+\s+)?evidenze\s+con\s+supporto\s+parziale,?\s+"
                r"(?:[a-z0-9]+\s+)?candidate\s+non\s+verificabile,?\s+"
                r"(?:[a-z0-9]+\s+)?associazioni\s+a\s+trial\s+e\s+"
                r"(?:[a-z0-9]+\s+)?relazioni\s+kg-only",
                r"(?:patient\s+)?eligibility\s+(?:was|is|has\s+been)\s+not\s+(?:evaluated|assessed)",
                r"(?:patient\s+)?eligibility\s+has\s+not\s+been\s+(?:evaluated|assessed)",
                r"(?:the\s+)?(?:trial\s+)?association\s+(?:does\s+not|cannot)\s+establish\s+(?:efficacy|eligibility|response)",
                r"efficacy\s+(?:is|has\s+been)\s+not\s+established\s+by\s+this\s+trial",
            ]
            if trial.get("nct_id"):
                allowed.append(rf"il\s+trial\s+{re.escape(str(trial['nct_id']).casefold())}\s+è\s+associato\s+al\s+caso")
                allowed.append(rf"la\s+candidate\s+è\s+associata\s+al\s+trial\s+{re.escape(str(trial['nct_id']).casefold())}")
                conditions = [re.escape(str(value).strip().casefold())
                              for value in trial.get("conditions") or [] if str(value).strip()]
                if conditions:
                    condition = "(?:" + "|".join(conditions) + ")"
                    condition_list = rf"(?:il\s+)?{condition}(?:\s+e\s+(?:il\s+)?{condition})*"
                    condition_suffix = (
                        rf"(?:\s+per\s+(?:(?:pazienti\s+con|il\s+trattamento\s+di)\s+)?{condition_list}"
                        rf"|,\s+che\s+(?:riguarda\s+pazienti\s+con|include\s+(?:diverse\s+condizioni\s+tra\s+cui|tra\s+le\s+condizioni))\s+{condition_list})"
                    )
                    allowed.append(
                        rf"la\s+candidate\s+è\s+associata\s+al\s+trial\s+"
                        rf"{re.escape(str(trial['nct_id']).casefold())}{condition_suffix}"
                    )
            if candidate.get("canonical_status") == "CONTEXT_ONLY":
                allowed.append(r"lo\s+stato\s+canonico\s+è\s+di\s+solo\s+contesto")
            if trial.get("eligibility_status") == "NOT_EVALUATED":
                allowed.append(r"l['’]eleggibilità\s+del\s+paziente\s+non\s+è\s+stata\s+valutata")
            if summary_facts:
                trial_count = summary_facts.get("trial_count")
                kg_count = summary_facts.get("kg_only_count")
                paper_count = summary_facts.get("paper_count")
                if type(trial_count) is int and type(kg_count) is int:
                    prefix = r"il\s+dossier\s+comprende\s+"
                    suffix = (rf"{trial_count}\s+associazioni\s+a\s+trial\s+e\s+"
                              rf"{kg_count}\s+relazioni\s+del\s+knowledge\s+graph")
                    if paper_count in (None, 0):
                        allowed.append(prefix + suffix)
                    if type(paper_count) is int:
                        allowed.append(prefix + rf"{paper_count}\s+relazioni\s+da\s+pubblicazioni,\s+" + suffix)
                    if paper_count == 0:
                        allowed.append(r"le\s+evidenze\s+riportate\s+derivano\s+da\s+associazioni\s+a\s+trial\s+clinici,\s+"
                                       r"le\s+quali\s+non\s+costituiscono\s+prova\s+di\s+efficacia")
                    if kg_count > 0:
                        allowed.append(r"non\s+è\s+disponibile\s+la\s+provenienza\s+documentale\s+per\s+le\s+relazioni\s+"
                                       r"derivate\s+esclusivamente\s+dal\s+knowledge\s+graph")
                        allowed.append(r"le\s+limitazioni\s+includono\s+l['’]assenza\s+di\s+provenienza\s+documentale\s+"
                                       r"per\s+alcune\s+relazioni\s+e\s+il\s+fatto\s+che\s+"
                                       r"l['’]associazione\s+a\s+trial\s+non\s+costituisce\s+prova\s+di\s+efficacia")
            if object_pattern:
                allowed.append(
                    rf"(?:the|this|a)?\s*trial(?:\s+record)?\s+(?:includes|lists|investigates|studies|evaluates)\s+"
                    rf"(?:the\s+)?(?:{object_pattern})"
                )
            sentences = [part.strip().rstrip(".!? ").casefold() for part in
                         re.split(r"(?<=[.!?;])\s+|\n+", text or "") if part.strip()]
            for sentence in sentences:
                licensed = any(re.fullmatch(pattern, sentence) for pattern in allowed)
                if not licensed:
                    # Conjunction never licenses an unknown assertion: each
                    # complete clause must independently match the closed grammar.
                    clauses = re.split(r"\s+e\s+", sentence)
                    licensed = len(clauses) > 1 and all(
                        any(re.fullmatch(pattern, clause) for pattern in allowed)
                        for clause in clauses
                    )
                if not licensed:
                    violations.append({"candidate_id": candidate.get("candidate_id"),
                                       "kind": "TRIAL_ASSOCIATION_SCOPE_UNPROVEN",
                                       "text": sentence})
            if not violations:
                return violations
        efficacy_text = re.sub(
            r"\b(?:not|no|without|non)\s+(?:an?\s+)?(?:efficacy|effective|effectiveness|proof\s+of\s+efficacy|efficacia|efficace|beneficio\s+clinico)\b"
            r"|\b(?:does\s+not|doesn't|did\s+not|didn't)\s+(?:demonstrate|show)\s+(?:efficacy|benefit)\b"
            r"|\bnon\s+(?:dimostra|è\s+una\s+prova\s+di|costituisce\s+(?:una\s+)?prova\s+di)\s+(?:efficacia|beneficio)\b",
            lambda m: m.group(0) if lx.ends_in_local_negation(lowered[:m.start()]) else " ",
            lowered,
        )
        efficacy = re.findall(
            r"\b(?:efficacy|effective|effectiveness|response\s+rate|clinical\s+benefit|therapeutic\s+response|showed\s+benefit|suitable\s+for\s+treatment|would\s+benefit|efficacia|efficace|beneficio\s+clinico|risposta\s+terapeutica|beneficio\s+terapeutico)\b",
            efficacy_text,
        )
        if efficacy:
            violations.append({"candidate_id": candidate.get("candidate_id"),
                               "kind": "TRIAL_EFFICACY_ESCALATION", "phrases": efficacy})
        positive_eligibility = re.search(
            r"\b(?:the\s+)?(?:patient|participant|subject|paziente|partecipante)\s+(?:is|appears|seems|è|e|sembra)\s+"
            r"(?:eligible|qualified)\b|\b(?:would\s+be\s+)?(?:eligible|qualified)\b|"
            r"\b(?:would\s+)?qualif(?:y|ies)\s+for\b|\b(?:could|can)\s+enroll\b|"
            r"\bmeets?\s+(?:the\s+)?eligibility\s+criteria\b|\b(?:eleggibile|idone[oa]|può\s+essere\s+arruolat[oa]|soddisfa)\b",
            lowered,
        )
        if trial.get("eligibility_status") == "NOT_EVALUATED" and positive_eligibility:
            violations.append({"candidate_id": candidate.get("candidate_id"),
                               "kind": "TRIAL_ELIGIBILITY_ESCALATION"})
    elif branch == "KG_ONLY":
        if re.search(r"\bcontext[_ -]?only\b", lowered):
            violations.append({"candidate_id": candidate.get("candidate_id"),
                               "kind": "KG_ONLY_STATUS_MISMATCH",
                               "expected": "KG_ONLY"})
        # Remove only the explicit absence clause.  A later documentary claim
        # must remain visible, even when the same paragraph contains negation.
        documentary_text = re.sub(
            r"\b(?:non\s+(?:è|sono)\s+supportat[oaie]\s+da\s+evidenz[ae]\s+documental[ei]"
            r"|not\s+supported\s+by\s+(?:the\s+)?documentary\s+evidence)\b",
            lambda match: match.group(0) if lx.ends_in_local_negation(lowered[:match.start()]) else " ",
            lowered,
        )
        documentary = re.findall(
            r"\b(?:validated\s+(?:quote|evidence|source)|documentary\s+evidence|documented\s+evidence|paper\s+evidence|source[- ]grounded|evidenza\s+documentale|evidenza\s+da\s+documento|supportata\s+dalla\s+letteratura|"
            r"supported\s+by\s+(?:the\s+)?(?:graph\s+and\s+)?(?:the\s+)?literature|paper\s+confirms)\b",
            documentary_text,
        )
        if documentary:
            violations.append({"candidate_id": candidate.get("candidate_id"),
                               "kind": "KG_DOCUMENTARY_ESCALATION", "phrases": documentary})
    return violations


# ══════════════════════════════════════════════════════════════════ verify

def _check_global_counts(narrative, narrator_input):
    """Audit explicit numbers in the closed legacy summary templates."""
    facts = _summary_facts(narrator_input.get("candidates") or [])
    patterns = {
        "paper_count": r"(\d+)\s+relazioni\s+da\s+pubblicazioni",
        "trial_count": r"(\d+)\s+associazioni\s+a\s+trial",
        "kg_only_count": r"(\d+)\s+relazioni\s+del\s+knowledge\s+graph",
        "validated_quote_count": r"(\d+)\s+citazioni\s+validate",
        "partial_support_count": r"(\d+)\s+relazioni\s+(?:con\s+supporto\s+parziale|hanno\s+un\s+supporto\s+parziale)",
        "no_support_count": r"(\d+)\s+non\s+hanno\s+supporto",
        "unverifiable_count": r"(\d+)\s+sono\s+non\s+verificabili",
    }
    violations = []
    for label, text in _narrative_texts(narrative):
        if label.startswith("candidate:"):
            continue
        for key, pattern in patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = int(match.group(1))
                if value != facts[key]:
                    violations.append({"block": label, "fact": key,
                                       "expected": facts[key], "observed": value})
    return violations


def _unlicensed_global_text(text: str, narrator_input: dict[str, Any]) -> str:
    """Separate verified dossier-wide facts from candidate-scoped claims.

    Only complete closed clauses with values grounded in the canonical
    projection are removed. Unknown prose still reaches all restrictive
    checks; a correct count cannot license a malicious suffix.
    """
    facts = narrator_input.get("summary_facts") or {}
    small_numbers = ("zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette",
                     "otto", "nove", "dieci", "undici", "dodici", "tredici", "quattordici",
                     "quindici", "sedici", "diciassette", "diciotto", "diciannove", "venti")

    def number(key: str) -> str:
        value = facts.get(key)
        if type(value) is not int or value < 0:
            return r"(?!)"
        alternatives = [str(value)]
        if value < len(small_numbers):
            alternatives.append(small_numbers[value])
        return "(?:" + "|".join(alternatives) + ")"

    allowed = [
        rf"sono presenti {number('validated_quote_count')} citazioni validate",
        rf"sono presenti {number('partial_support_count')} relazioni con supporto parziale "
        rf"e {number('validated_quote_count')} citazioni validate",
    ]
    # A conservative lower bound: unsupported/unverifiable PAPER and KG-only
    # rows suffice. TRIAL rows never count as unsupported efficacy evidence.
    majority_fields = [facts.get(key) for key in (
        "candidate_count", "no_support_count", "unverifiable_count", "kg_only_count")]
    if (all(type(value) is int and value >= 0 for value in majority_fields)
            and sum(majority_fields[1:]) > majority_fields[0] / 2):
        allowed.append(r"il sistema ha identificato che la maggior parte delle relazioni "
                       r"non ha supporto documentale o non è verificabile")
    if facts.get("contradictory_count") == 0:
        allowed.append(
            rf"l['’]analisi mostra che {number('partial_support_count')} relazioni hanno un supporto parziale, "
            rf"{number('no_support_count')} non hanno supporto, "
            rf"{number('unverifiable_count')} sono non verificabili "
            r"e non sono state riscontrate relazioni contraddittorie"
        )
    required_limits = {"CANDIDATE_PARTIALLY_SUPPORTED", "DOCUMENT_PROVENANCE_NOT_AVAILABLE",
                       "DOCUMENT_UNAVAILABLE", "QUOTE_INVALID", "READER_ABSTAINED"}
    if required_limits.issubset(set(narrator_input.get("limitations") or [])):
        allowed.append(
            r"il dossier presenta diverse limitazioni: alcune candidate sono solo parzialmente supportate, "
            r"per altre non è disponibile la provenienza documentale o il documento stesso, "
            r"e (?:in vari casi sono state riscontrate citazioni non valide o l['’]astensione del lettore"
            r"|in alcuni casi le citazioni non sono state validate o il lettore ha espresso astensione)"
        )
    unlicensed = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", lx.normalize(text or "")):
        normalized = sentence.strip().rstrip(".!?; ").casefold()
        if normalized and not any(re.fullmatch(pattern, normalized) for pattern in allowed):
            unlicensed.append(sentence)
    return "\n".join(unlicensed)


def verify_narrative(
    canonical_dossier: dict[str, Any],
    narrator_input: dict[str, Any],
    narrative_output: dict[str, Any] | None,
) -> dict[str, Any]:
    """``NarrativeVerificationResult``. Deterministico: nessun LLM, nessuna rete."""
    if isinstance(narrative_output, dict) and "controlled_contract" in narrative_output:
        from .controlled import verify_controlled

        return verify_controlled(narrator_input, narrative_output)
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
    reason_codes: list[str] = _check_generated_contract(narrative_output, narrator_input)
    global_fact_mismatches = _check_global_counts(narrative_output, narrator_input)
    if global_fact_mismatches:
        reason_codes.append("NARRATIVE_GLOBAL_FACT_MISMATCH")

    unknown_ids, missing_ids, duplicate_ids = _check_candidate_ids(narrative_output, narrator_input)
    if unknown_ids:
        reason_codes.append(REASON_UNKNOWN_CANDIDATE)
    if missing_ids:
        reason_codes.append(REASON_MISSING_CANDIDATE)
    if duplicate_ids:
        reason_codes.append(REASON_DUPLICATE_CANDIDATE)

    unauthorized_entities = _check_entities(narrative_output, narrator_input, allowed)
    if unauthorized_entities:
        reason_codes.append(REASON_UNAUTHORIZED_ENTITY)

    recommendation_language = _check_recommendation(narrative_output)
    if recommendation_language:
        reason_codes.append(REASON_UNAUTHORIZED_RECOMMENDATION)

    summary_status_claims = _check_summary_status_claim(narrative_output)
    if summary_status_claims:
        reason_codes.append(REASON_SUMMARY_STATUS_CLAIM)

    unauthorized_quotes, promoted_quotes = _check_quotes(
        narrative_output, canonical_dossier or {}, allowed, narrator_input)
    if unauthorized_quotes:
        reason_codes.append(REASON_UNAUTHORIZED_QUOTE)
    if promoted_quotes:
        reason_codes.append(REASON_REJECTED_QUOTE_PROMOTED)

    unauthorized_source_refs, source_ref_type_mismatches = _check_source_refs(narrative_output, narrator_input)
    if unauthorized_source_refs:
        reason_codes.append(REASON_UNAUTHORIZED_SOURCE_REF)
    if source_ref_type_mismatches:
        reason_codes.append(REASON_SOURCE_REF_TYPE_MISMATCH)

    by_id = {c["candidate_id"]: dict(c) for c in narrator_input.get("candidates") or []}
    # Legacy free-form callbacks still need the deterministic safety checks.
    # These internal constraints are not narrator facts or scientific endpoints.
    # The canonical controlled narrator uses the closed documentary catalog.
    if narrator_input.get("documentary_contract_version"):
        for entry in (canonical_dossier or {}).get("paper_evidence") or []:
            candidate = by_id.get(entry.get("candidate_id"))
            if candidate is not None:
                candidate["candidate_support"] = {"result": entry.get("support_level")}
                candidate["contradiction_present"] = entry.get("contradiction_present")
    text_by_id: dict[str, str] = {}
    for entry in narrative_output.get("candidate_narratives") or []:
        cid = entry.get("candidate_id")
        text_by_id[cid] = f"{text_by_id.get(cid, '')}\n{candidate_text(entry)}".strip()

    escalations, support_escalations, inversions, negations_lost, omissions = [], [], [], [], []
    branch_violations: list[dict[str, Any]] = []
    global_status_escalations: list[dict[str, Any]] = []
    global_support_escalations: list[dict[str, Any]] = []
    global_text = "\n".join(
        str(narrative_output.get(key) or "")
        for key in ("narrative_summary", "limitations_summary", "closing_note")
    )
    global_text = _unlicensed_global_text(global_text, narrator_input)
    candidate_results = []
    for cid, candidate in by_id.items():
        text = text_by_id.get(cid, "")
        association_only = (
            candidate.get("branch") == "TRIAL"
            and (candidate.get("trial_context") or {}).get("evidence_interpretation")
            == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
        )
        safe_trial_text = association_only and not _check_branch_semantics(candidate, text)
        c_esc = [] if safe_trial_text else _check_status(candidate, text)
        c_support = [] if safe_trial_text else _check_support_level(candidate, text)
        c_inv, c_lost = _check_polarity(candidate, text)
        c_omit = _check_omissions(candidate, text)
        branch_text = text
        if candidate.get("branch") in {"TRIAL", "KG_ONLY"}:
            branch_text += "\n" + global_text
        c_branch = _check_branch_semantics(candidate, branch_text, narrator_input.get("summary_facts"))
        g_esc: list[dict[str, Any]] = []
        g_support: list[dict[str, Any]] = []
        if global_text:
            # Global prose has no candidate identity; apply the same checks
            # conservatively to every restricted candidate in the dossier.
            g_esc = _check_status(candidate, global_text)
            g_support = _check_support_level(candidate, global_text)
            global_status_escalations += g_esc
            global_support_escalations += g_support
            escalations += g_esc
            support_escalations += g_support
        escalations += c_esc
        support_escalations += c_support
        inversions += c_inv
        negations_lost += c_lost
        omissions += c_omit
        branch_violations += c_branch
        candidate_results.append({
            "candidate_id": cid,
            "canonical_status": candidate["canonical_status"],
            "support_direction": candidate["support_direction"],
            "narrated": bool(text),
            "status_escalation": bool(c_esc),
            "support_level_escalation": bool(c_support),
            "global_status_escalation": bool(g_esc),
            "global_support_level_escalation": bool(g_support),
            "polarity_inversion": bool(c_inv),
            "negation_lost": bool(c_lost),
            "critical_omissions": [o["omitted"] for o in c_omit],
        })

    if escalations:
        reason_codes.append(REASON_STATUS_ESCALATION)
    if support_escalations:
        reason_codes.append(REASON_SUPPORT_LEVEL_ESCALATION)
    if inversions:
        reason_codes.append(REASON_POLARITY_INVERSION)
    if negations_lost:
        reason_codes.append(REASON_NEGATION_LOST)
    if omissions:
        reason_codes.append(REASON_CRITICAL_OMISSION)
    for violation in branch_violations:
        if violation["kind"] == "TRIAL_EFFICACY_ESCALATION":
            reason_codes.append(REASON_TRIAL_EFFICACY_ESCALATION)
        elif violation["kind"] == "TRIAL_ASSOCIATION_SCOPE_UNPROVEN":
            reason_codes.append("NARRATIVE_TRIAL_ASSOCIATION_SCOPE_UNPROVEN")
        elif violation["kind"] == "TRIAL_ELIGIBILITY_ESCALATION":
            reason_codes.append(REASON_TRIAL_ELIGIBILITY_ESCALATION)
        elif violation["kind"] == "KG_DOCUMENTARY_ESCALATION":
            reason_codes.append(REASON_KG_DOCUMENTARY_ESCALATION)
        elif violation["kind"] == "KG_ONLY_STATUS_MISMATCH":
            reason_codes.append(REASON_KG_STATUS_MISMATCH)

    return {
        "status": FAIL if reason_codes else PASS,
        "reason_codes": sorted(set(reason_codes)),
        "global_fact_mismatches": global_fact_mismatches,
        "candidate_results": candidate_results,
        "unknown_candidate_ids": unknown_ids,
        "missing_candidate_ids": missing_ids,
        "duplicate_candidate_ids": duplicate_ids,
        "unauthorized_entities": unauthorized_entities,
        "status_escalations": escalations,
        "support_level_escalations": support_escalations,
        "global_status_escalations": global_status_escalations,
        "global_support_level_escalations": global_support_escalations,
        "polarity_violations": inversions + negations_lost,
        "unauthorized_quotes": unauthorized_quotes + promoted_quotes,
        "unauthorized_source_refs": unauthorized_source_refs,
        "source_ref_type_mismatches": source_ref_type_mismatches,
        "recommendation_language": recommendation_language,
        "summary_status_claims": summary_status_claims,
        "critical_omissions": omissions,
        "branch_semantic_violations": branch_violations,
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
