import os
import sys
import pandas as pd

# Open the output file in UTF-8 mode and redirect sys.stdout
sys.stdout = open('inspection_results_utf8.txt', 'w', encoding='utf-8')

def inspect_file(path, sep='\t'):
    print(f"\n{'='*60}")
    print(f"FILE: {os.path.basename(path)}")
    print(f"PATH: {path}")
    print(f"{'='*60}")

    df_dict = {}
    
    if path.endswith('.xlsx'):
        try:
            xl = pd.ExcelFile(path)
            sheets = xl.sheet_names
            print(f"Fogli trovati: {sheets}")
            for sheet in sheets:
                print(f"\n--- Foglio: {sheet} ---")
                df = pd.read_excel(path, sheet_name=sheet)
                df_dict[f"{os.path.basename(path)} [{sheet}]"] = df
                _run_inspection(df)
        except Exception as e:
            print(f"ERRORE di caricamento XLSX: {str(e)}")
    else:
        # Tenta il caricamento con varianti
        df = None
        encodings = ['utf-8', 'latin-1', 'cp1252']
        separators = [sep, None]
        
        loaded = False
        last_err = None
        
        for s in separators:
            for enc in encodings:
                try:
                    if s is None:
                        df = pd.read_csv(path, sep=None, engine='python', encoding=enc, low_memory=False, on_bad_lines='skip')
                        print(f"Caricato con successo usando sep=Auto-detect, encoding={enc}")
                    else:
                        df = pd.read_csv(path, sep=s, encoding=enc, low_memory=False, on_bad_lines='skip')
                        print(f"Caricato con successo usando sep={repr(s)}, encoding={enc}")
                    loaded = True
                    break
                except Exception as e:
                    last_err = e
            if loaded:
                break
                
        if not loaded:
            print(f"ERRORE CRITICO di caricamento: {str(last_err)}")
            return None
            
        df_dict[os.path.basename(path)] = df
        _run_inspection(df)
        
    return df_dict

def _run_inspection(df):
    # 1. Dimensioni
    print(f"\n[DIMENSIONI]")
    print(f"  Righe: {len(df):,}")
    print(f"  Colonne: {len(df.columns)}")

    # 2. Schema colonne
    print(f"\n[SCHEMA COLONNE]")
    for col in df.columns:
        dtype = str(df[col].dtype)
        n_null = df[col].isna().sum()
        pct_null = round(n_null / len(df) * 100, 1) if len(df) > 0 else 0.0
        n_unique = df[col].nunique()
        print(f"  {col:<45} dtype={dtype:<10} null={pct_null}%  unique={n_unique:,}")

    # 3. Prime 3 righe
    print(f"\n[PRIME 3 RIGHE]")
    print(df.head(3).to_string())

    # 4. Colonne con troppi null (>50%)
    if len(df) > 0:
        high_null = [c for c in df.columns if df[c].isna().sum()/len(df) > 0.5]
    else:
        high_null = []
    if high_null:
        print(f"\n[ATTENZIONE - colonne con >50% null]")
        for c in high_null:
            print(f"  - {c}")

    # 5. Campione valori per colonne chiave (prime 5 colonne)
    print(f"\n[CAMPIONE VALORI - prime 5 colonne]")
    for col in df.columns[:5]:
        sample = df[col].dropna().unique()[:5].tolist()
        print(f"  {col}: {sample}")

def main():
    base_dir = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI"
    
    files = [
        os.path.join(base_dir, "cancerGeneList.tsv"),
        os.path.join(base_dir, "companion_diagnostic_devices.tsv"),
        os.path.join(base_dir, "fda_approved_oncology_therapies.xlsx"),
        os.path.join(base_dir, "Civic", "01-May-2026-AcceptedClinicalEvidenceSummaries.tsv"),
        os.path.join(base_dir, "Civic", "01-May-2026-FeatureSummaries.tsv"),
        os.path.join(base_dir, "Civic", "01-May-2026-MolecularProfileSummaries.tsv"),
        os.path.join(base_dir, "Civic", "01-May-2026-VariantSummaries.tsv"),
        os.path.join(base_dir, "DGIdb", "categories.tsv"),
        os.path.join(base_dir, "DGIdb", "drugs.tsv"),
        os.path.join(base_dir, "DGIdb", "genes.tsv"),
        os.path.join(base_dir, "DGIdb", "interactions.tsv"),
    ]
    
    for f in files:
        if not os.path.exists(f):
            print(f"ERRORE: Il file non esiste -> {f}")
            continue
        inspect_file(f)

if __name__ == "__main__":
    main()
