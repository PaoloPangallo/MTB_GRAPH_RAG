"""Policy lessicale del Narrative Verifier — esplicita, versionata, testabile.

Non è un classificatore clinico. È un elenco chiuso di pattern, scelto perché
verificabile: ogni voce può essere mostrata a un revisore, discussa e cambiata.
Un modello che giudica un altro modello non darebbe questa proprietà.

Il limite è dichiarato: copre le formulazioni elencate, non la lingua italiana o
inglese in generale. Vedi ``docs/dossier_narrator/12_limitations.md``.
"""

from __future__ import annotations

import re
import unicodedata

LEXICON_VERSION = "narrative-lexicon/1.7"


def normalize(text: str) -> str:
    """Normalizzazione Unicode NFC prima di ogni confronto.

    In italiano ``è`` può arrivare come carattere precomposto (U+00E8) oppure
    come ``e`` seguito da accento combinante (U+0065 U+0300). Sono la stessa
    lettera per un lettore e due stringhe diverse per una regex: senza NFC un
    modello che usasse la seconda forma avrebbe aggirato l'intera policy
    scrivendo «è indicato» in modo indistinguibile a occhio nudo.
    """
    return unicodedata.normalize("NFC", text or "")


def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(normalize(p), re.IGNORECASE) for p in patterns)


# ─────────────────────────────────────────── §14 linguaggio prescrittivo
#
# Il dossier canonico non contiene alcuna recommendation clinica (verificato in
# `00_current_dossier_contract.md`): qualunque formulazione prescrittiva nella
# narrativa è quindi non autorizzata, senza eccezioni da modellare.

RECOMMENDATION_PATTERNS: tuple[str, ...] = (
    # inglese
    r"\bis\s+recommended\b", r"\bwe\s+recommend\b", r"\brecommended\s+(?:therapy|treatment|option)\b",
    r"\bshould\s+(?:receive|be\s+treated|be\s+given|be\s+offered|be\s+started)\b",
    r"\bshould\s+be\s+considered\s+for\s+treatment\b",
    r"\bmust\s+(?:receive|be\s+treated)\b",
    r"\bindicated\s+(?:treatment|therapy)\b", r"\bis\s+(?:clinically\s+)?indicated\b",
    r"\bbest\s+(?:treatment|therapy|option)\b", r"\bpreferred\s+(?:therapy|treatment)\b",
    r"\bstandard\s+of\s+care\b", r"\bfirst[- ]line\s+(?:choice|therapy\s+of\s+choice)\b",
    r"\btreatment\s+of\s+choice\b",
    # italiano
    r"\bsi\s+raccomanda\b", r"\bè\s+raccomandat[oa]\b", r"\braccomandiamo\b",
    r"\bterapia\s+raccomandata\b", r"\bopzione\s+raccomandata\b",
    r"\b(?:il\s+)?paziente\s+dovrebbe\s+(?:ricevere|essere\s+trattat)",
    r"\bdovrebbe\s+essere\s+trattat[oa]\b", r"\bdeve\s+essere\s+trattat[oa]\b",
    r"\bè\s+indicat[oa]\b", r"\bterapia\s+(?:migliore|di\s+scelta|d[ie]\s+elezione)\b",
    r"\bstandard\s+di\s+cura\b", r"\bprima\s+linea\s+di\s+scelta\b",
)

# ─────────────────────────────────────────── §11 escalation di status
#
# Formulazioni che affermano supporto stabilito. Sono un problema soltanto per
# le candidate il cui dossier NON esprime supporto: il verifier le cerca solo lì.

SUPPORT_CLAIM_PATTERNS: tuple[str, ...] = (
    # inglese
    r"\b(?:strongly|firmly|clearly|well|robustly)\s+support(?:ed|s)?\b",
    r"\bis\s+support(?:ed)\b", r"\bconfirm(?:ed|s)\b", r"\bestablished\b",
    r"\bproven\b", r"\bdemonstrat(?:ed|es)\s+efficacy\b",
    r"\b(?:is|are)\s+(?:clinically\s+)?effective\b",
    r"\bdefinitely\s+(?:sensitive|resistant)\b",
    r"\bprimary\s+therapeutic\s+option\b", r"\bfda[- ]approved\b",
    r"\bevidence\s+(?:strongly\s+)?supports\b",
    # italiano
    r"\b(?:fortemente|chiaramente|solidamente|pienamente)\s+support",
    r"\bè\s+supportat[oa]\b", r"\bconfermat[oa]\b", r"\bconsolidat[oa]\b",
    r"\bdimostrat[oa]\s+efficac", r"\bè\s+(?:clinicamente\s+)?efficace\b",
    r"\bsicuramente\s+(?:sensibile|resistente)\b",
    r"\bopzione\s+terapeutica\s+primaria\b", r"\bapprovato\s+dalla\s+fda\b",
    r"\bl[ae]\s+evidenz[ae]\s+support",
)

# Affermazioni di completezza/certezza. Sono valutate solo quando i campi
# strutturati del dossier non autorizzano supporto pieno.
SUPPORT_LEVEL_ESCALATION_PATTERNS: tuple[str, ...] = (
    r"\b(?:pienamente|completamente|definitivamente)\s+supportat[oa]\b",
    r"\b(?:pienamente|completamente|definitivamente)\s+confermat[oa]\b",
    r"\blivello\s+di\s+evidenza\s+(?:alto|forte|definitiv[oa])\b",
    r"\b(?:evidenza|supporto)\s+(?:alto|forte|definitiv[oa])\b",
    r"\b(?:fully|completely|definitively)\s+(?:supported|confirmed)\b",
    r"\b(?:high|strong|definitive)\s+level\s+of\s+evidence\b",
    r"\b(?:il\s+)?supporto\s+(?:documentale\s+)?(?:Ã¨\s+)?(?:completo|pieno)\b",
    r"\b(?:full|complete)\s+(?:documentary\s+)?support\b",
)

# Il summary globale è introduttivo: non può sintetizzare lo stato documentale
# delle candidate, perché non è legato deterministicamente a una candidate.
SUMMARY_STATUS_CLAIM_PATTERNS: tuple[str, ...] = (
    r"\ble\s+evidenze\s+conferma(?:no|te|ta|to)\b",
    r"\b(?:l[ae]|le)\s+evidenz[ae]\s+(?:supporta|supportano|supportat[aeoi])\b",
    r"\b(?:la|le)\s+documentazione\s+(?:supporta|supportano|conferma|confermano|dimostra|dimostrano)\b",
    r"\bla\s+fonte\s+(?:supporta|conferma|dimostra)\b",
    r"\bla\s+terapia\s+risulta\s+supportat[aeoa]\b",
    r"\b(?:le|la)\s+evidenz[ae]\s+(?:non\s+supporta|non\s+conferma|contraddice|sono\s+contraddittori)\b",
    r"\b(?:nessun|nessuna)\s+(?:supporto|evidenza)\b",
    r"\b(?:evidenza|documentazione|fonte)\s+(?:is\s+)?(?:supported|confirms|demonstrates|contradictory)\b",
    r"\b(?:the\s+)?evidence\s+(?:supports|confirms|demonstrates|does\s+not\s+support)\b",
)

# ─────────────────────────────────────────── §12 marcatori di negazione
#
# Presenti quando la narrativa preserva correttamente una polarità negativa.

NEGATION_MARKER_PATTERNS: tuple[str, ...] = (
    r"\bnon\s+support", r"\bnon\s+conferma", r"\bnon\s+sostiene\b",
    r"\bnon\s+è\s+stato\s+trovato\b", r"\bnessun\s+support", r"\bassenza\s+di\s+support",
    r"\bdoes\s+not\s+support\b", r"\bno\s+support\b", r"\bnot\s+supported\b",
    r"\bfails\s+to\s+support\b", r"\bwithout\s+support\b",
    r"\bcontraddi", r"\bcontradict",
)

# Contesto negativo specifico per i match di ``confermata/o``: senza questa
# regola ``non è confermata`` contiene comunque il token positivo e può essere
# scambiato per escalation di status.
NEGATED_CONFIRMATION_PATTERNS: tuple[str, ...] = (
    r"\bnon\s+(?:è\s+)?confermat[oa]\b",
    r"\bnon\s+è\s+stat[oa]\s+confermat[oa]\b",
    r"\bnon\s+risultan[oa]\s+conferm",
)

#: Marcatori che segnalano incertezza. Attesi quando lo status è AMBIGUOUS.
UNCERTAINTY_MARKER_PATTERNS: tuple[str, ...] = (
    r"\bambigu", r"\bincert", r"\bnon\s+determinat", r"\bnon\s+conclusiv",
    r"\bnon\s+è\s+possibile\s+(?:stabilire|concludere)\b",
    r"\buncertain\b", r"\binconclusive\b", r"\bunclear\b", r"\bnot\s+determined\b",
)

#: Marcatori di assenza di supporto documentale. Attesi quando non esiste una
#: quote validata.
#
# La variante «segnale documentale» è stata aggiunta dopo la **prima run LIVE**
# del benchmark: il modello aveva scritto «non è stato trovato un segnale
# documentale esplicito», che dichiara correttamente l'assenza di citazione
# validata, e il verifier la contava come omissione. Era un falso positivo del
# lexicon, non un'infedeltà del modello — ed è esattamente ciò per cui esiste un
# benchmark. La regola resta stretta: serve una negazione esplicita accanto a un
# sostantivo documentale.
NO_DOCUMENT_MARKER_PATTERNS: tuple[str, ...] = (
    r"\bnessuna\s+citazion", r"\bnessun\s+documento\b", r"\bnon\s+.{0,24}citazione\s+validat",
    r"\bnon\s+.{0,30}(?:supporto|segnale|riscontro|evidenza)\s+documental",
    r"\bnessun\s+(?:supporto|segnale|riscontro)\s+documental",
    r"\bsenza\s+(?:supporto|segnale)\s+documental",
    r"\bno_document_signal\b",
    r"\bastension", r"\bastenut", r"\bsi\s+è\s+astenut",
    r"\bno\s+validated\s+quote\b", r"\bno\s+documentary\s+(?:support|signal)\b", r"\babstain",
)

RECOMMENDATION_RE = _compile(RECOMMENDATION_PATTERNS)
SUPPORT_CLAIM_RE = _compile(SUPPORT_CLAIM_PATTERNS)
SUPPORT_LEVEL_ESCALATION_RE = _compile(SUPPORT_LEVEL_ESCALATION_PATTERNS)
SUPPORT_COMPLETENESS_RE = re.compile(
    r"\bsupporto\b.{0,24}\b(?:completo|pieno)\b|\b(?:full|complete)\s+support\b",
    re.IGNORECASE | re.DOTALL,
)
SUMMARY_STATUS_CLAIM_RE = _compile(SUMMARY_STATUS_CLAIM_PATTERNS)
NEGATION_MARKER_RE = _compile(NEGATION_MARKER_PATTERNS)
NEGATED_CONFIRMATION_RE = _compile(NEGATED_CONFIRMATION_PATTERNS)
UNCERTAINTY_MARKER_RE = _compile(UNCERTAINTY_MARKER_PATTERNS)
NO_DOCUMENT_MARKER_RE = _compile(NO_DOCUMENT_MARKER_PATTERNS)


def _hits(text: str, compiled: tuple[re.Pattern[str], ...]) -> list[str]:
    normalized = normalize(text)
    found: list[str] = []
    for pattern in compiled:
        match = pattern.search(normalized)
        if match:
            found.append(match.group(0).strip())
    return found


def recommendation_hits(text: str) -> list[str]:
    """Formulazioni prescrittive trovate."""
    text = re.sub(r'\b[èe]\s+indicato\s+che\s+si\s+tratta\b',
                  'è riportato che si tratta', normalize(text), flags=re.IGNORECASE)
    text = re.sub(r'\bla\s+corrispondenza\s+(?:con|per)\s+la\s+malattia\s+[èe]\s+indicata\s+come\s+(?:(?:non\s+)?confermata|ancora\s+da\s+confermare)\b',
                  'la corrispondenza è riportata nei controlli', text, flags=re.IGNORECASE)
    return _hits(text, RECOMMENDATION_RE)


LOCAL_NEGATION_RE = re.compile(
    r"\b(?:non(?:\s+(?:è|sono|sia|siano|era|erano|ha|hanno|aveva|avevano|stata|stato|stati|state|mai)){0,3}"
    r"|not(?:\s+(?:been|yet))?)\s+$", re.IGNORECASE,
)


def ends_in_local_negation(prefix: str) -> bool:
    """A local negation chain, bounded by punctuation and lexical auxiliaries."""
    return bool(LOCAL_NEGATION_RE.search(normalize(prefix)))


def support_claim_hits(text: str) -> list[str]:
    """Affermazioni di supporto stabilito trovate."""
    text = normalize(text)
    hits = []
    for pattern in SUPPORT_CLAIM_RE:
        for match in pattern.finditer(text):
            # Negation governs this occurrence only. It cannot cancel a
            # positive assertion elsewhere, across punctuation, or after
            # ``non solo`` / ``not false that``.
            prefix = text[:match.start()]
            negation = LOCAL_NEGATION_RE.search(prefix)
            if negation:
                preceding = prefix[:negation.start()]
                if not ends_in_local_negation(preceding):
                    continue
            hits.append(match.group(0).strip())
    return hits


def support_level_escalation_hits(text: str) -> list[str]:
    """Formulazioni di supporto pieno o di evidenza forte."""
    normalized = normalize(text)
    hits = _hits(normalized, SUPPORT_LEVEL_ESCALATION_RE)
    for match in SUPPORT_COMPLETENESS_RE.finditer(normalized):
        if not ends_in_local_negation(normalized[:match.start()]):
            hits.append(match.group(0).strip())
    return list(dict.fromkeys(hits))


def summary_status_claim_hits(text: str) -> list[str]:
    """Claim documentali vietati nel summary non candidate-bound."""
    return _hits(text, SUMMARY_STATUS_CLAIM_RE)


def has_negation_marker(text: str) -> bool:
    return bool(_hits(text, NEGATION_MARKER_RE))


def has_negated_confirmation(text: str) -> bool:
    """Indica che ``confermata/o`` è usato in una costruzione negativa."""
    return bool(_hits(text, NEGATED_CONFIRMATION_RE))


def has_uncertainty_marker(text: str) -> bool:
    return bool(_hits(text, UNCERTAINTY_MARKER_RE))


def has_no_document_marker(text: str) -> bool:
    return bool(_hits(text, NO_DOCUMENT_MARKER_RE))
