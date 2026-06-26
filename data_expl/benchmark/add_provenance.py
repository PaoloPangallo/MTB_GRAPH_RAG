import pandas as pd
from pathlib import Path

# Path al CSV
csv_path = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")

# Legge il CSV
df = pd.read_csv(csv_path)

# Aggiunge le due nuove colonne di provenance
# 1. drug_source: è il PMID del trial registrativo già presente nella colonna pmid
df["drug_source"] = "PMID: " + df["pmid"].astype(str)

# 2. escat_source: visto che è stato copiato da un DB non ricordato,
# lo dichiariamo onestamente per evitare di "fabbricare" una provenienza basata su IASLC.
df["escat_source"] = "Aggregated Clinical Database (unspecified)"

# Ordina le colonne in modo logico, mettendo le source vicino a drug ed escat
cols = df.columns.tolist()
# Spostiamo drug_source subito dopo expected_drug
idx_drug = cols.index("expected_drug")
cols.insert(idx_drug + 1, cols.pop(cols.index("drug_source")))

# Spostiamo escat_source subito dopo escat
idx_escat = cols.index("escat")
cols.insert(idx_escat + 1, cols.pop(cols.index("escat_source")))

df = df[cols]

# Salva sovrascrivendo la v2 in modo pulito
df.to_csv(csv_path, index=False)
print(f"Aggiornato CSV in: {csv_path}")
print(df[["case_id", "expected_drug", "drug_source", "escat", "escat_source"]].head())
