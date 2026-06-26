import sys
from pathlib import Path

# Aggiungi il path per poter importare backend
sys.path.append(str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))

from backend.pipeline.agents.synthesizer import filtra_pmid_non_verificati

# Set di PMID verificati nel KG di test (7-9 cifre)
verified_pmids = {11111111, 22222222, 33333333, 23982599}

# Casi di test
test_cases = [
    # 1. Formati standard singoli
    ("Esempio standard 1: [PMID: 11111111] (verificato).", "Esempio standard 1: [PMID: 11111111] (verificato).", []),
    ("Esempio standard 2: [PMID: 99999999] (non verificato).", "Esempio standard 2: [PMID: [PMID non verificato nel KG]] (non verificato).", [99999999]),
    ("Esempio standard 3: PMID 22222222 (verificato).", "Esempio standard 3: PMID 22222222 (verificato).", []),
    ("Esempio standard 4: PMID 88888888 (non verificato).", "Esempio standard 4: PMID [PMID non verificato nel KG] (non verificato).", [88888888]),
    ("Esempio standard 5: **PMID: 33333333** (verificato).", "Esempio standard 5: **PMID: 33333333** (verificato).", []),
    ("Esempio standard 6: **PMID: 77777777** (non verificato).", "Esempio standard 6: **PMID: [PMID non verificato nel KG]** (non verificato).", [77777777]),
    
    # 2. Formato auto-correzione Qwen
    ("Esempio auto-correzione: [PMID: 66666666 — non presente nel KG]", "Esempio auto-correzione: [PMID: [PMID non verificato nel KG] — non presente nel KG]", [66666666]),
    
    # 3. Liste con prefisso singolo (separatori vari)
    ("Lista virgole: [PMID: 11111111, 99999999]", "Lista virgole: [PMID: 11111111, [PMID non verificato nel KG]]", [99999999]),
    ("Lista punti e virgola: [PMID: 11111111; 22222222; 88888888]", "Lista punti e virgola: [PMID: 11111111; 22222222; [PMID non verificato nel KG]]", [88888888]),
    
    # 4. Nuovi casi critici: Liste in grassetto markdown sparse
    ("Grassetto sparso: **23982599**, **24263064**, **24439929**", "Grassetto sparso: **23982599**, **[PMID non verificato nel KG]**, **[PMID non verificato nel KG]**", [24263064, 24439929]),
    
    # 5. Nuovi casi critici: PMID dentro URL
    ("URL PubMed: pubmed.ncbi.nlm.nih.gov/25989278 (non verificato)", "URL PubMed: pubmed.ncbi.nlm.nih.gov/[PMID non verificato nel KG] (non verificato)", [25989278]),
    ("URL PubMed verificato: pubmed.ncbi.nlm.nih.gov/23982599", "URL PubMed verificato: pubmed.ncbi.nlm.nih.gov/23982599", []),
    
    # 6. Nuovi casi critici: Numero nudo in lista
    ("Numero nudo in lista: 23982599, 27959700, [38942080]", "Numero nudo in lista: 23982599, [PMID non verificato nel KG], [[PMID non verificato nel KG]]", [27959700, 38942080]),
    
    # 7. Sicurezza: Numeri non PMID da preservare (Anni, NCT ID)
    ("Anno: Nel 2018 è stato pubblicato lo studio.", "Anno: Nel 2018 è stato pubblicato lo studio.", []),
    ("NCT ID: trial NCT04027309 (non deve essere toccato).", "NCT ID: trial NCT04027309 (non deve essere toccato).", []),
]

print("="*60)
print("AVVIO TEST DEL NUOVO FILTRO PMID (STRATEGIA ALL-NUMBERS)")
print("="*60)

all_passed = True
for i, (text, expected_text, expected_rimossi) in enumerate(test_cases, 1):
    filtrato, rimossi = filtra_pmid_non_verificati(text, verified_pmids)
    print(f"\nCaso {i}:")
    print(f"  Input:     {text}")
    print(f"  Output:    {filtrato}")
    print(f"  Rimossi:   {rimossi}")
    
    # Verifica correttezza testo
    if filtrato != expected_text:
        print(f"  [ERRORE TESTO] Atteso: {expected_text}")
        all_passed = False
    
    # Verifica log rimozioni
    if rimossi != expected_rimossi:
        print(f"  [ERRORE RIMOZIONI] Attesi rimossi: {expected_rimossi}")
        all_passed = False

print("\n" + "="*60)
if all_passed:
    print("TEST COMPLETATO CON SUCCESSO! Tutte le asserzioni sono verificate.")
else:
    print("TEST FALLITO! Controllare gli errori sopra.")
print("="*60)
sys.exit(0 if all_passed else 1)
