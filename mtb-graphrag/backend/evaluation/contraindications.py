# Dizionario delle controindicazioni e farmaci non raccomandati per i casi del benchmark.
# Mappa il case_id a una lista di farmaci (nomi normalizzati) che sono considerati un errore medico
# se raccomandati, ad esempio a causa di mutazioni di resistenza note nel caso.

CONTRAINDICATIONS = {
    "BENCH-011": ["erlotinib", "gefitinib", "afatinib", "dacomitinib"],  # EGFR T790M resistance
    "BENCH-013": ["crizotinib", "alectinib", "ceritinib", "brigatinib"],  # ALK G1202R resistance
    "BENCH-014": ["imatinib", "dasatinib", "nilotinib", "bosutinib"],  # ABL1 T315I resistance
    "BENCH-019": ["imatinib"],  # KIT Exon 9 (often requires higher dose or sunitinib, standard imatinib might be considered sub-optimal/contraindicated in some strict contexts, but definitely sunitinib is expected)
    # Casi base senza particolari resistenze note a priori nel contesto
    "BENCH-001": [],
    "BENCH-002": [],
    "BENCH-003": [],
    "BENCH-004": [],
    "BENCH-005": [],
    "BENCH-006": [],
    "BENCH-007": [],
    "BENCH-008": [],
    "BENCH-009": [],
    "BENCH-010": [],
    "BENCH-012": [],
    "BENCH-015": [],
    "BENCH-016": [],
    "BENCH-017": [],
    "BENCH-018": [],
    "BENCH-020": [],
    "BENCH-021": [],
    "BENCH-022": [],
    "BENCH-023": [],
    "BENCH-024": [],
    "BENCH-025": [],
    "BENCH-026": [],
    "BENCH-027": [],
    "BENCH-028": [],
    "BENCH-029": [],
    "BENCH-030": [],
}

def get_contraindications(case_id: str) -> list[str]:
    """Restituisce la lista di farmaci controindicati per il caso specificato."""
    return CONTRAINDICATIONS.get(case_id, [])
