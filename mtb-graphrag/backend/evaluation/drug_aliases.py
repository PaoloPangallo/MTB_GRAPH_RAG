# Dizionario di normalizzazione dei farmaci
# Mappa nomi commerciali o alias al nome generico atteso nel benchmark

DRUG_ALIASES = {
    # EGFR inhibitors
    "tagrisso": "osimertinib",
    "tarceva": "erlotinib",
    "iressa": "gefitinib",
    "vizimpro": "dacomitinib",
    "gilotrif": "afatinib",

    # ALK/ROS1 inhibitors
    "alecensa": "alectinib",
    "xalkori": "crizotinib",
    "lorbrena": "lorlatinib",
    "zykadia": "ceritinib",
    "alunbrig": "brigatinib",

    # BRAF/MEK inhibitors
    "zelboraf": "vemurafenib",
    "tafinlar": "dabrafenib",
    "mekinist": "trametinib",
    "braftovi": "encorafenib",
    "mektovi": "binimetinib",
    "cotellic": "cobimetinib",

    # HER2 targeted
    "herceptin": "trastuzumab",
    "perjeta": "pertuzumab",
    "kadcyla": "trastuzumab emtansine",
    "t-dm1": "trastuzumab emtansine",
    "enhertu": "trastuzumab deruxtecan",
    "tukysa": "tucatinib",
    "nerlynx": "neratinib",
    "tykerb": "lapatinib",

    # BCR-ABL inhibitors
    "gleevec": "imatinib",
    "glivec": "imatinib",
    "sprycel": "dasatinib",
    "tasigna": "nilotinib",
    "bosulif": "bosutinib",
    "iclusig": "ponatinib",
    "scemblix": "asciminib",

    # PARP inhibitors
    "lynparza": "olaparib",
    "rubraca": "rucaparib",
    "zejula": "niraparib",
    "talzenna": "talazoparib",

    # Checkpoint inhibitors
    "keytruda": "pembrolizumab",
    "opdivo": "nivolumab",
    "tecentriq": "atezolizumab",
    "imfinzi": "durvalumab",
    "bavencio": "avelumab",

    # PI3K/AKT/mTOR
    "piqray": "alpelisib",
    "truqap": "capivasertib",
    "afinitor": "everolimus",

    # FLT3 inhibitors
    "xospata": "gilteritinib",
    "rydapt": "midostaurin",

    # KRAS G12C
    "lumakras": "sotorasib",
    "krazati": "adagrasib",

    # RET inhibitors
    "retevmo": "selpercatinib",
    "gavreto": "pralsetinib",

    # TRK inhibitors
    "vitrakvi": "larotrectinib",
    "rozlytrek": "entrectinib",

    # VEGF/Multi-kinase
    "sutent": "sunitinib",
    "nexavar": "sorafenib",
    "lenvima": "lenvatinib",
    "stivarga": "regorafenib",
    "cabometyx": "cabozantinib",

    # Others
    "tibsovo": "ivosidenib",
    "pemazyre": "pemigatinib",
    "tabrecta": "capmatinib",
    "tepmtko": "tepotinib",
    "erbitux": "cetuximab",
    "vectibix": "panitumumab",
    "faslodex": "fulvestrant"
}

def normalize_drug_name(drug_name: str) -> str:
    """Normalizza un nome di farmaco nel suo equivalente atteso in lowercase."""
    if not drug_name:
        return ""
    d_lower = drug_name.strip().lower()
    return DRUG_ALIASES.get(d_lower, d_lower)

def parse_drug_combinations(drug_string: str) -> list[str]:
    """Converte una stringa come 'Trastuzumab+Pertuzumab' o 'Drug A and Drug B' in una lista normalizzata."""
    if not drug_string:
        return []
    
    # Sostituisci i separatori comuni con il '+'
    s = drug_string.lower().replace(" and ", "+").replace(",", "+").replace("/", "+").replace("&", "+")
    parts = [normalize_drug_name(p) for p in s.split("+")]
    return [p for p in parts if p]
