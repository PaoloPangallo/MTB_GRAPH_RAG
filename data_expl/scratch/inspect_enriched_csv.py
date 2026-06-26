import pandas as pd
import os

CSV_DIR = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI\Clean_Graph_Data"
EVIDENCE_PATH = os.path.join(CSV_DIR, "node_evidence.csv")

def verify():
    df = pd.read_csv(EVIDENCE_PATH)
    
    # Filter for OncoKB evidence
    df_oncokb = df[df['source_type'] == 'OncoKB']
    
    print("==========================================================================")
    print("VERIFICA SCHEMA E VOCABOLARIO PER NODI EVIDENCE ONCOKB")
    print("==========================================================================")
    print(f"Totale nodi inseriti: {len(df_oncokb)}")
    print("\n--- DETTAGLIO RECORD INSERITI ---")
    
    columns_to_show = [
        'evidence_id', 'evidence_type', 'evidence_level', 'evidence_direction', 
        'significance', 'disease', 'doid', 'source_type', 'rating'
    ]
    
    # Pretty print the table using pandas formatting
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df_oncokb[columns_to_show].to_string(index=False))
    
    print("\n--- VERIFICA COERENZA VOCABOLARIO ---")
    
    # Check evidence_type
    unique_types = df['evidence_type'].unique()
    oncokb_types = df_oncokb['evidence_type'].unique()
    print(f"1. evidence_type in OncoKB: {oncokb_types}")
    print(f"   Coerente con vocabolario generale? {all(t in unique_types for t in oncokb_types)}")
    
    # Check significance
    unique_sigs = df['significance'].dropna().unique()
    oncokb_sigs = df_oncokb['significance'].unique()
    print(f"2. significance in OncoKB: {oncokb_sigs}")
    print(f"   Coerente con vocabolario generale? {all(s in unique_sigs for s in oncokb_sigs)}")
    
    # Check evidence_direction
    unique_dirs = df['evidence_direction'].dropna().unique()
    oncokb_dirs = df_oncokb['evidence_direction'].unique()
    print(f"3. evidence_direction in OncoKB: {oncokb_dirs}")
    print(f"   Coerente con vocabolario generale? {all(d in unique_dirs for d in oncokb_dirs)}")
    
    # Check DOID presence
    print("4. DOID null check:")
    print(f"   Ci sono DOID vuoti nei record OncoKB? {df_oncokb['doid'].isna().any()}")
    
    # Check rating
    print("5. Rating values in OncoKB:")
    print(f"   Valori rating: {df_oncokb['rating'].unique()} (Attesi interi da 1 a 5)")
    
    print("==========================================================================")

if __name__ == "__main__":
    verify()
