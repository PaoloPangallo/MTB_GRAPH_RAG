"""Confronto fra denominazioni di malattia, senza fondere entita' distinte.

Il problema concreto: il gold scrive "intrahepatic cholangiocarcinoma", il grafo
"Cholangiolocellular Carcinoma"; il gold scrive "advanced NSCLC", il grafo
"Lung Non-small Cell Carcinoma". Trattare tutto come uguale nasconderebbe una
divergenza reale; trattare tutto come diverso seppellirebbe il segnale sotto il
rumore lessicale.

La via seguita separa tre cose che spesso vengono confuse:

1. **vocabolario** - due nomi della stessa entita' (NSCLC / Lung Non-small Cell
   Carcinoma). Equivalenza ammessa, e limitata a un elenco esplicito.
2. **specificita'** - un sottotipo e il suo genitore (intrahepatic cholangiocarcinoma
   vs cholangiocarcinoma). **Non** e' equivalenza: viene segnalata come tale, perche'
   e' esattamente la distinzione che il caso K1 richiede di preservare.
3. **qualificatori** - stadio e setting incollati al nome ("advanced", "resected").
   Vengono estratti e mandati alla dimensione qualificatori, che lo schema non modella.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import norm_text

IDENTICAL = "identical"
SAME_ENTITY = "same_entity_different_vocabulary"
DIFFERENT_SPECIFICITY = "different_specificity"
DISTINCT = "distinct"

# Aggettivi di stadio/setting che si attaccano al nome della malattia. Non fanno
# parte dell'identita' dell'entita': vengono estratti come qualificatori.
_QUALIFIER_PATTERNS = (
    r"locally\s+advanced",
    r"completely\s+resected",
    r"surgically\s+unresectable",
    r"advanced",
    r"metastatic",
    r"unresectable",
    r"resected",
    r"recurrent",
    r"refractory",
    r"relapsed",
    r"previously\s+treated",
    r"treatment[-\s]na(?:i|ï)ve",
    r"stage\s+[iv]+[ab]?(?:\s*[-–]\s*[iv]+[ab]?)?",
    # Stato del biomarcatore incollato al nome ("ALK-positive NSCLC"). E' una
    # proprieta' del tumore, non una malattia diversa, ed e' gia' confrontato sulla
    # dimensione variante/profilo: lasciarlo qui produrrebbe conflitti fantasma.
    r"\b[a-z0-9]{2,6}[-\s](?:positive|negative|mutated|mutant|rearranged|altered|driven)\b",
)

# Nomi diversi della stessa entita'. Ogni gruppo va giustificato: sono sinonimi di
# vocabolario, non sottotipi.
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "nsclc",
            "non-small cell lung cancer",
            "non small cell lung cancer",
            "lung non-small cell carcinoma",
            "non-small cell lung carcinoma",
            "nsclc lung cancer",
        }
    ),
    frozenset({"lung adenocarcinoma", "adenocarcinoma of the lung"}),
    frozenset({"cholangiocarcinoma", "cca", "bile duct cancer", "biliary tract cancer"}),
    frozenset(
        {
            "intrahepatic cholangiocarcinoma",
            "icca",
            "intrahepatic bile duct carcinoma",
        }
    ),
)

# Sottotipo -> entita' genitore. Serve a riconoscere che due nomi sono imparentati
# *senza* dichiararli equivalenti.
_SUBTYPE_OF: dict[str, str] = {
    "intrahepatic cholangiocarcinoma": "cholangiocarcinoma",
    "extrahepatic cholangiocarcinoma": "cholangiocarcinoma",
    "cholangiolocellular carcinoma": "cholangiocarcinoma",
    "perihilar cholangiocarcinoma": "cholangiocarcinoma",
    "lung adenocarcinoma": "nsclc",
    "lung squamous cell carcinoma": "nsclc",
}


@dataclass(frozen=True)
class DiseaseTerm:
    raw: str
    core: str
    qualifiers: tuple[str, ...]


def split_disease(value: object) -> DiseaseTerm:
    """Separa il nome dell'entita' dai qualificatori di stadio/setting."""
    raw = "" if value is None else str(value)
    working = norm_text(raw)
    found: list[str] = []
    for pattern in _QUALIFIER_PATTERNS:
        match = re.search(pattern, working, flags=re.IGNORECASE)
        if match:
            found.append(match.group(0).strip())
            working = re.sub(pattern, " ", working, flags=re.IGNORECASE)
    core = norm_text(re.sub(r"\s*,\s*", " ", working).strip(" ,;-"))
    return DiseaseTerm(raw=raw, core=core, qualifiers=tuple(sorted(set(found))))


def _canonical_group(core: str) -> frozenset[str] | None:
    for group in _SYNONYM_GROUPS:
        if core in group:
            return group
    return None


def _parent(core: str) -> str | None:
    if core in _SUBTYPE_OF:
        return _SUBTYPE_OF[core]
    group = _canonical_group(core)
    if group:
        for member in group:
            if member in _SUBTYPE_OF:
                return _SUBTYPE_OF[member]
    return None


def _same_entity(left: str, right: str) -> bool:
    if left == right:
        return True
    group = _canonical_group(left)
    return bool(group and right in group)


def disease_relation(left: object, right: object) -> str:
    """Relazione fra due denominazioni: identica, stesso ente, sottotipo, distinta."""
    first = split_disease(left)
    second = split_disease(right)
    if not first.core or not second.core:
        return DISTINCT
    if first.core == second.core:
        return IDENTICAL
    if _same_entity(first.core, second.core):
        return SAME_ENTITY

    left_parent = _parent(first.core)
    right_parent = _parent(second.core)
    if left_parent and _same_entity(left_parent, second.core):
        return DIFFERENT_SPECIFICITY
    if right_parent and _same_entity(right_parent, first.core):
        return DIFFERENT_SPECIFICITY
    if left_parent and right_parent and _same_entity(left_parent, right_parent):
        return DIFFERENT_SPECIFICITY
    return DISTINCT


def diseases_match(left: object, right: object) -> bool:
    """Match ammesso solo per identita' o differenza di solo vocabolario.

    Un sottotipo non fa match con il suo genitore: e' la regola che impedisce di
    considerare equivalenti intrahepatic cholangiocarcinoma e un colangiocarcinoma
    qualunque.
    """
    return disease_relation(left, right) in {IDENTICAL, SAME_ENTITY}
