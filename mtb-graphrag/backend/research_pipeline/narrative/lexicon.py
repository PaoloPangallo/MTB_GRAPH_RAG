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

LEXICON_VERSION = "narrative-lexicon/1.0"


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

#: Marcatori che segnalano incertezza. Attesi quando lo status è AMBIGUOUS.
UNCERTAINTY_MARKER_PATTERNS: tuple[str, ...] = (
    r"\bambigu", r"\bincert", r"\bnon\s+determinat", r"\bnon\s+conclusiv",
    r"\bnon\s+è\s+possibile\s+(?:stabilire|concludere)\b",
    r"\buncertain\b", r"\binconclusive\b", r"\bunclear\b", r"\bnot\s+determined\b",
)

#: Marcatori di assenza di supporto documentale. Attesi quando non esiste una
#: quote validata.
NO_DOCUMENT_MARKER_PATTERNS: tuple[str, ...] = (
    r"\bnessuna\s+citazion", r"\bnessun\s+documento\b", r"\bnon\s+.{0,24}citazione\s+validat",
    r"\bnon\s+è\s+stato\s+trovato\s+supporto\s+documental", r"\bsenza\s+supporto\s+documental",
    r"\bastension", r"\bastenut", r"\bsi\s+è\s+astenut",
    r"\bno\s+validated\s+quote\b", r"\bno\s+documentary\s+support\b", r"\babstain",
)

RECOMMENDATION_RE = _compile(RECOMMENDATION_PATTERNS)
SUPPORT_CLAIM_RE = _compile(SUPPORT_CLAIM_PATTERNS)
NEGATION_MARKER_RE = _compile(NEGATION_MARKER_PATTERNS)
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
    return _hits(text, RECOMMENDATION_RE)


def support_claim_hits(text: str) -> list[str]:
    """Affermazioni di supporto stabilito trovate."""
    return _hits(text, SUPPORT_CLAIM_RE)


def has_negation_marker(text: str) -> bool:
    return bool(_hits(text, NEGATION_MARKER_RE))


def has_uncertainty_marker(text: str) -> bool:
    return bool(_hits(text, UNCERTAINTY_MARKER_RE))


def has_no_document_marker(text: str) -> bool:
    return bool(_hits(text, NO_DOCUMENT_MARKER_RE))
