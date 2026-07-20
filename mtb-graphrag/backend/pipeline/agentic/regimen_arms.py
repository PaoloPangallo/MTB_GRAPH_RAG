"""Rappresentazione strutturata dei bracci di uno studio e confronto
deterministico della claim del KG contro il regime di ciascun braccio.

Sostituisce completamente l'estrazione di farmaci basata su token generici
(catene testuali connesse da "and"/"+"/virgole nel testo grezzo), che produceva
falsi positivi sistematici:

- MARIPOSA: osimertinib è il comparatore, non parte del regime
  amivantamab + lazertinib — un'estrazione piatta univa erroneamente i
  farmaci di bracci diversi in un solo insieme.
- RELAY: parole generiche del testo ("hospitals", "double-blind", "EGFR",
  "enrolled", "progression-free") venivano trattate come componenti
  farmacologici.

Qui un termine diventa un "intervento" SOLO se compare nel vocabolario
controllato ``KNOWN_INTERVENTIONS`` sotto — mai per presenza generica in una
catena testuale.
"""

from __future__ import annotations

from typing import Any, Literal

ArmMatch = Literal["exact", "partial", "no_match", "unknown"]

# Vocabolario controllato di farmaci/interventi oncologici riconosciuti.
# Qualunque termine riportato da un braccio che non compaia qui (dopo
# normalizzazione case-insensitive) viene scartato: non diventa mai un
# "farmaco" ai fini del confronto deterministico. Vocabolario finito e
# specifico al dominio NSCLC/EGFR di questo dimostratore: va esteso se si
# aggiungono altri contesti tumorali.
KNOWN_INTERVENTIONS: frozenset[str] = frozenset({
    "amivantamab", "lazertinib", "osimertinib", "erlotinib", "gefitinib",
    "dacomitinib", "afatinib", "ramucirumab", "carboplatin", "carboplatino",
    "cisplatin", "cisplatino", "pemetrexed", "paclitaxel", "docetaxel",
    "bevacizumab", "nivolumab", "pembrolizumab", "atezolizumab",
    "durvalumab", "crizotinib", "alectinib", "brigatinib", "lorlatinib",
    "trastuzumab", "trastuzumab deruxtecan", "sotorasib", "adagrasib",
    "capmatinib", "tepotinib", "selpercatinib", "pralsetinib", "dabrafenib",
    "trametinib", "vemurafenib", "cobimetinib", "entrectinib", "larotrectinib",
    "amivantamab-vmjw",
})

# Termini che possono comparire in un braccio di studio ma non sono un
# farmaco della claim (comparatore inerte): mai trattati come intervento.
_NON_DRUG_ARM_TERMS: frozenset[str] = frozenset({"placebo", "best supportive care", "observation"})


def normalize_intervention_name(value: Any) -> str | None:
    """Normalizza un nome grezzo e lo valida contro il vocabolario
    controllato. Restituisce ``None`` se non è un farmaco/intervento
    riconosciuto o se è un termine non farmacologico (es. "placebo")."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text or text in _NON_DRUG_ARM_TERMS:
        return None
    return text if text in KNOWN_INTERVENTIONS else None


def normalize_source_arms(raw_arms: Any) -> list[dict[str, Any]]:
    """Normalizza e valida ``source_arms`` grezzo (es. dalla risposta LLM):
    ogni braccio diventa ``{"arm_name": str, "interventions": list[str]}``,
    con interventi filtrati contro il vocabolario controllato. Bracci senza
    nome o senza alcun intervento riconosciuto vengono scartati."""
    if not isinstance(raw_arms, list):
        return []
    arms: list[dict[str, Any]] = []
    for entry in raw_arms:
        if not isinstance(entry, dict):
            continue
        arm_name = entry.get("arm_name")
        if not isinstance(arm_name, str) or not arm_name.strip():
            continue
        raw_interventions = entry.get("interventions")
        if not isinstance(raw_interventions, list):
            continue
        interventions = sorted({
            normalized
            for value in raw_interventions
            if (normalized := normalize_intervention_name(value)) is not None
        })
        arms.append({"arm_name": arm_name.strip(), "interventions": interventions})
    return arms


def claim_components_from_object(text: str) -> set[str]:
    """Estrae i componenti della CLAIM del KG (non del testo grezzo della
    fonte): il campo ``EvidenceItem.object`` è dato strutturato del knowledge
    graph, non testo libero — split su connettori standard e validazione
    contro il vocabolario controllato, per restare coerenti col resto del
    modulo (mai un termine fuori vocabolario)."""
    import re
    parts = re.split(r"[+,/]|(?:\band\b)", text or "", flags=re.IGNORECASE)
    components = set()
    for part in parts:
        normalized = normalize_intervention_name(part.strip())
        if normalized is not None:
            components.add(normalized)
    return components


def match_claim_to_arms(claim_components: set[str], arms: list[dict[str, Any]]) -> ArmMatch:
    """Confronta deterministicamente la claim contro OGNI braccio
    separatamente — mai unendo i farmaci di bracci diversi in un solo
    insieme, cosa che fonderebbe erroneamente un comparatore col braccio
    sperimentale (es. MARIPOSA: osimertinib con amivantamab+lazertinib).

    - "exact": la claim coincide esattamente con l'insieme di un braccio.
    - "partial": la claim è un sottoinsieme proprio di un braccio (il
      braccio ha componenti aggiuntivi non nella claim) o viceversa, oppure
      condivide componenti con un braccio senza coincidere.
    - "no_match": nessun braccio condivide alcun componente con la claim.
    - "unknown": non ci sono bracci noti da confrontare.
    """
    if not arms:
        return "unknown"
    arm_sets = [set(arm["interventions"]) for arm in arms if arm["interventions"]]
    if not arm_sets:
        return "unknown"

    for arm_set in arm_sets:
        if claim_components and claim_components == arm_set:
            return "exact"

    for arm_set in arm_sets:
        if claim_components and arm_set and (claim_components < arm_set or arm_set < claim_components):
            return "partial"

    for arm_set in arm_sets:
        if claim_components & arm_set:
            return "partial"

    return "no_match"
