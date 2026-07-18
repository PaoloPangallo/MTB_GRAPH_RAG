import requests
import json
import time
import re
import sys
import pandas as pd
from pathlib import Path

# Dual writer to capture log in UTF-8
sys.stdout.reconfigure(encoding='utf-8')
log_file_path = 'download_trials_log.txt'
sys.stdout = open(log_file_path, 'w', encoding='utf-8')

print("============================================================")
print("CLINICALTRIALS.GOV DUMP DOWNLOADER & PIPELINE")
print("============================================================")

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# Oncological genes to search for
GENE_TERMS = [
    "EGFR", "BRCA1", "BRCA2", "KRAS", "ALK", "BRAF", "TP53",
    "ERBB2", "HER2", "MET", "RET", "NRAS", "PIK3CA", "PTEN",
    "IDH1", "IDH2", "FGFR", "CDK4", "CDK6", "PDGFRA",
    "KIT", "ABL1", "JAK2", "FLT3", "NPM1", "DNMT3A",
    "ATM", "PALB2", "RAD51", "NTRK1", "NTRK2", "NTRK3",
    "ROS1", "NF1", "VHL", "APC", "SMAD4", "POLE"
]

FIELDS = "NCTId,BriefTitle,OverallStatus,Phase,Condition,InterventionName,EligibilityCriteria,Keyword"

PARAMS = {
    "query.cond": "cancer OR neoplasm OR carcinoma OR leukemia OR lymphoma OR sarcoma OR glioma OR melanoma",
    "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING",
    "fields": FIELDS,
    "pageSize": 1000,
    "format": "json"
}

all_studies = []
gene_stats = {}

print("Step 1: Download paginato in corso...")

for gene in GENE_TERMS:
    print(f"\nScaricando trial per gene: {gene}")
    params = PARAMS.copy()
    params["query.term"] = gene
    next_token = None
    page = 0
    gene_studies_count = 0

    while True:
        if next_token:
            params["pageToken"] = next_token
        elif "pageToken" in params:
            del params["pageToken"]

        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            if response.status_code == 429:
                print("  Rate limit superato (429). Attesa di 2 secondi...")
                time.sleep(2.0)
                continue
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"  Errore durante il download per {gene}: {e}")
            break

        studies = data.get("studies", [])
        all_studies.extend(studies)
        gene_studies_count += len(studies)
        page += 1
        print(f"  Pagina {page}: {len(studies)} studi (parziale per {gene}: {gene_studies_count})")

        next_token = data.get("nextPageToken")
        if not next_token or len(studies) == 0:
            break

        time.sleep(0.3)  # rispetta i rate limit
        
    gene_stats[gene] = gene_studies_count

print(f"\nTotale studi scaricati (con duplicati): {len(all_studies)}")

# ------------------------------------------------------------
# Step 2: Pulizia e deduplicazione
# ------------------------------------------------------------
print("\nStep 2: Estrazione e deduplicazione...")

def extract_study(study):
    """Estrae i campi utili da un singolo studio JSON."""
    proto = study.get("protocolSection", {})

    id_mod = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    cond_mod = proto.get("conditionsModule", {})
    design_mod = proto.get("designModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    elig_mod = proto.get("eligibilityModule", {})

    # Interventi: lista di nomi farmaci
    interventions = arms_mod.get("interventions", [])
    intervention_names = [i.get("name", "") for i in interventions if i.get("name")]

    # Fasi: lista → stringa
    phases = design_mod.get("phases", [])
    phase_str = ", ".join(phases) if phases else "NA"

    # Condizioni
    conditions = cond_mod.get("conditions", [])

    # Keywords
    keywords = cond_mod.get("keywords", [])

    return {
        "nct_id": id_mod.get("nctId", ""),
        "title": id_mod.get("briefTitle", ""),
        "status": status_mod.get("overallStatus", ""),
        "phase": phase_str,
        "conditions": " | ".join(conditions),
        "keywords": " | ".join(keywords),
        "interventions": " | ".join(intervention_names),
        "eligibility_criteria": elig_mod.get("eligibilityCriteria", ""),
    }

records = [extract_study(s) for s in all_studies]
df = pd.DataFrame(records)
df = df[df["nct_id"] != ""].drop_duplicates(subset=["nct_id"]).copy()
print(f"Studi unici dopo deduplicazione: {len(df)}")

# Check limit to notify
if len(df) > 50000:
    print("\n[ATTENZIONE] Il numero totale di studi unici supera 50.000!")

# ------------------------------------------------------------
# Step 3: Estrazione relazioni Gene dai criteri di eleggibilità
# ------------------------------------------------------------
print("\nStep 3: Estrazione relazioni Gene dai criteri di eleggibilità...")

ONCOGENES = [
    "EGFR", "BRCA1", "BRCA2", "KRAS", "ALK", "BRAF", "TP53",
    "ERBB2", "HER2", "MET", "RET", "NRAS", "PIK3CA", "PTEN",
    "IDH1", "IDH2", "FGFR1", "FGFR2", "FGFR3", "CDK4", "CDK6",
    "PDGFRA", "KIT", "ABL1", "JAK2", "FLT3", "NPM1", "DNMT3A",
    "ATM", "PALB2", "NTRK1", "NTRK2", "NTRK3", "ROS1", "NF1",
    "VHL", "APC", "SMAD4", "POLE", "MLH1", "MSH2", "MSH6",
    "RAD51", "CHEK2", "STK11", "KEAP1", "CDKN2A", "MYC"
]

def extract_genes_from_text(text):
    if not text:
        return []
    found = set()
    for gene in ONCOGENES:
        # Cerca il gene come parola intera, case-sensitive
        if re.search(r'\b' + re.escape(gene) + r'\b', text):
            found.add(gene)
    return sorted(found)

edge_gene_rows = []
for _, row in df.iterrows():
    text = f"{row['eligibility_criteria']} {row['keywords']} {row['title']}"
    genes = extract_genes_from_text(text)
    mapped_genes = set()
    for gene in genes:
        # HER2 is an alias for ERBB2 in node_gene.csv
        symbol = "ERBB2" if gene == "HER2" else gene
        mapped_genes.add(symbol)
    for gene in sorted(mapped_genes):
        edge_gene_rows.append({
            "nct_id": row["nct_id"],
            "gene_symbol": gene,
            "source": "eligibility_criteria"
        })

df_edge_gene = pd.DataFrame(edge_gene_rows)
print(f"Archi trial→gene estratti: {len(df_edge_gene)}")

# ------------------------------------------------------------
# Step 4: Estrazione relazioni Drug dagli interventi
# ------------------------------------------------------------
print("\nStep 4: Estrazione relazioni Drug dagli interventi...")

output_dir = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI\Clean_Graph_Data")

# Load node_drug.csv to verify and match drug names
try:
    node_drug_path = output_dir / "node_drug.csv"
    df_node_drugs = pd.read_csv(node_drug_path)
    # Collect all valid uppercase drug names
    valid_drug_names = set(df_node_drugs["drug_name"].dropna().str.upper())
    
    # Pre-build normalized mappings for fuzzy matching
    def normalize_name(name):
        if pd.isna(name):
            return ""
        val = str(name).upper().strip()
        val = re.sub(r'\b(HYDROCHLORIDE|SULFATE|TARTRATE|CITRATE|MALEATE|PHOSPHATE)\b', '', val)
        val = re.sub(r'[^A-Z0-9]', '', val)
        return val

    drug_norm_map = {normalize_name(name): name for name in valid_drug_names if normalize_name(name)}
    print(f"  Dizionario dei farmaci caricato da {node_drug_path.name}: {len(valid_drug_names)} farmaci unici.")
except Exception as e:
    print(f"  [ATTENZIONE] Impossibile caricare {node_drug_path}: {e}")
    valid_drug_names = set()
    drug_norm_map = {}

edge_drug_rows = []
for _, row in df.iterrows():
    if not row["interventions"]:
        continue
    drugs = [d.strip() for d in row["interventions"].split("|") if d.strip()]
    
    # Use a set to prevent duplicate edges of the same drug for the same trial
    seen_drugs_in_trial = set()
    
    for drug in drugs:
        skip_keywords = ["blood sample", "biopsy", "surgery", "radiation",
                         "questionnaire", "placebo", "standard of care",
                         "observation", "biobank", "imaging"]
        if any(kw in drug.lower() for kw in skip_keywords):
            continue
            
        # Try matching the whole intervention name
        matched_drugs = []
        norm_drug_raw = normalize_name(drug)
        
        if drug.upper() in valid_drug_names:
            matched_drugs.append(drug.upper())
        elif norm_drug_raw in drug_norm_map:
            matched_drugs.append(drug_norm_map[norm_drug_raw])
        else:
            # Tokenize by non-alphanumeric to find individual drugs in combination therapies or labels
            tokens = re.split(r'[^A-Z0-9]', drug.upper())
            for tok in tokens:
                tok = tok.strip()
                if len(tok) < 3:
                    continue
                norm_tok = normalize_name(tok)
                if norm_tok in drug_norm_map:
                    matched_drugs.append(drug_norm_map[norm_tok])
                    
        # Append all unique matched drugs
        for md in matched_drugs:
            if md not in seen_drugs_in_trial:
                edge_drug_rows.append({
                    "nct_id": row["nct_id"],
                    "drug_name_raw": drug,
                    "drug_name_normalized": md
                })
                seen_drugs_in_trial.add(md)

df_edge_drug = pd.DataFrame(edge_drug_rows)
print(f"Archi trial→drug estratti: {len(df_edge_drug)}")

# ------------------------------------------------------------
# Step 5: Statistiche e salvataggio
# ------------------------------------------------------------
print("\nStep 5: Salvataggio e compilazione statistiche finali...")

output_dir = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI\Clean_Graph_Data")
output_dir.mkdir(exist_ok=True)

# Nodi ClinicalTrial — senza eligibility_criteria
df_nodes = df[[
    "nct_id", "title", "status", "phase",
    "conditions", "keywords", "interventions"
]].copy()

# Esporta i CSV
df_nodes.to_csv(output_dir / "nodes_clinical_trials.csv", index=False, encoding='utf-8')
df_edge_gene.to_csv(output_dir / "edges_trial_gene.csv", index=False, encoding='utf-8')
df_edge_drug.to_csv(output_dir / "edges_trial_drug.csv", index=False, encoding='utf-8')
df[["nct_id", "eligibility_criteria"]].to_csv(
    output_dir / "trial_eligibility_criteria.csv", index=False, encoding='utf-8'
)

# Calcola distribuzioni
status_dist = df["status"].value_counts()
phase_dist = df["phase"].value_counts()

top_genes = df_edge_gene["gene_symbol"].value_counts().head(10)
top_drugs = df_edge_drug["drug_name_normalized"].value_counts().head(10)

print("\n=== CLASSIFICA DOWNLOAD PER GENE (QUERY) ===")
for g, count in gene_stats.items():
    print(f"  {g:<10} : {count:,} studi")

print("\n=== DISTRIBUZIONE PER STATO ===")
for status, count in status_dist.items():
    print(f"  {status:<30} : {count:,}")

print("\n=== DISTRIBUZIONE PER FASE ===")
for phase, count in phase_dist.items():
    print(f"  {phase:<30} : {count:,}")

print("\n=== TOP 10 GENI PIÙ FREQUENTI NEI CRITERI ===")
for g, count in top_genes.items():
    print(f"  {g:<10} : {count:,}")

print("\n=== TOP 10 FARMACI PIÙ FREQUENTI ===")
for d, count in top_drugs.items():
    print(f"  {d:<30} : {count:,}")

print("\n=== RIEPILOGO GENERALE ===")
print(f"Nodi ClinicalTrial:          {len(df_nodes):,}")
print(f"Archi ClinicalTrial→Gene:    {len(df_edge_gene):,}")
print(f"Archi ClinicalTrial→Drug:    {len(df_edge_drug):,}")
print(f"Gene unici trovati:          {df_edge_gene['gene_symbol'].nunique()}")
print(f"Drug unici (normalizzati):   {df_edge_drug['drug_name_normalized'].nunique()}")
print(f"Trial con almeno 1 gene:     {df_edge_gene['nct_id'].nunique()}")
print(f"Trial con almeno 1 drug:     {df_edge_drug['nct_id'].nunique()}")
print(f"\nFile salvati con successo in: {output_dir.absolute()}")
print("============================================================")
sys.stdout.close()
