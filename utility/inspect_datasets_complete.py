import os
import sys
import pandas as pd

# Reconfigure standard output streams to handle UTF-8 printing safely on Windows
sys.stdout.reconfigure(encoding='utf-8')

class DualWriter:
    """Helper to write simultaneously to stdout (console) and a log file."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        sys.stdout = self.terminal
        self.log.close()

def inspect_dataframe(df, name, details=""):
    print(f"\n{'='*80}")
    print(f"DATASET: {name} {details}")
    print(f"{'='*80}")

    # 1. Dimensions
    print(f"\n[DIMENSIONI]")
    print(f"  Righe: {len(df):,}")
    print(f"  Colonne: {len(df.columns)}")

    # 2. Column Schema
    print(f"\n[SCHEMA COLONNE]")
    for col in df.columns:
        dtype = str(df[col].dtype)
        n_null = df[col].isna().sum()
        pct_null = round(n_null / len(df) * 100, 1) if len(df) > 0 else 0.0
        n_unique = df[col].nunique()
        print(f"  {col:<45} dtype={dtype:<10} null={pct_null:>5}%  unique={n_unique:,}")

    # 3. First 3 Rows
    print(f"\n[PRIME 3 RIGHE]")
    if len(df) > 0:
        print(df.head(3).to_string())
    else:
        print("  (Tabella vuota)")

    # 4. High Null Column Warnings (>50%)
    if len(df) > 0:
        high_null = [c for c in df.columns if df[c].isna().sum()/len(df) > 0.5]
    else:
        high_null = []
    if high_null:
        print(f"\n[ATTENZIONE - colonne con >50% null]")
        for c in high_null:
            print(f"  - {c}")

    # 5. Value Samples for Key Columns (first 5 columns)
    print(f"\n[CAMPIONE VALORI - prime 5 colonne]")
    for col in df.columns[:5]:
        sample = df[col].dropna().unique()[:5].tolist()
        print(f"  {col}: {sample}")

def main():
    report_file = "dataset_inspection_report.txt"
    sys.stdout = DualWriter(report_file)

    print("================================================================================")
    print("ONCOLOGICAL DATASETS COMPLETE INSPECTION REPORT")
    print(f"Generato il: 2026-05-27 | File report: {report_file}")
    print("================================================================================\n")

    base_dir = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI"

    files_config = [
        {"path": "cancerGeneList.tsv", "sep": "\t", "index_col": None},
        {"path": "companion_diagnostic_devices.tsv", "sep": "\t", "index_col": None},
        {"path": "fda_approved_oncology_therapies.xlsx", "is_xlsx": True},
        {"path": "Civic/01-May-2026-AcceptedClinicalEvidenceSummaries.tsv", "sep": "\t", "index_col": None},
        {"path": "Civic/01-May-2026-FeatureSummaries.tsv", "sep": "\t", "index_col": None},
        {"path": "Civic/01-May-2026-MolecularProfileSummaries.tsv", "sep": "\t", "index_col": None},
        # For VariantSummaries, we use index_col=False to resolve the critical column-shifting issue!
        {"path": "Civic/01-May-2026-VariantSummaries.tsv", "sep": "\t", "index_col": False, "note": "(CARICATO CON index_col=False PER RISOLVERE LO SHIFT DELLE COLONNE)"},
        {"path": "DGIdb/categories.tsv", "sep": "\t", "index_col": None},
        {"path": "DGIdb/drugs.tsv", "sep": "\t", "index_col": None},
        {"path": "DGIdb/genes.tsv", "sep": "\t", "index_col": None},
        {"path": "DGIdb/interactions.tsv", "sep": "\t", "index_col": None},
    ]

    for f_conf in files_config:
        full_path = os.path.join(base_dir, f_conf["path"].replace("/", os.sep))
        filename = os.path.basename(full_path)

        if not os.path.exists(full_path):
            print(f"\nERRORE: Il file non esiste -> {full_path}")
            continue

        if f_conf.get("is_xlsx"):
            try:
                xl = pd.ExcelFile(full_path)
                print(f"\nFILE EXCEL RILEVATO: {filename}")
                print(f"Fogli trovati: {xl.sheet_names}")
                for sheet in xl.sheet_names:
                    df = pd.read_excel(full_path, sheet_name=sheet)
                    inspect_dataframe(df, filename, f"[Foglio: {sheet}]")
            except Exception as e:
                print(f"\nERRORE di caricamento Excel '{filename}': {str(e)}")
        else:
            # CSV / TSV Loading
            df = None
            encodings = ['utf-8', 'latin-1', 'cp1252']
            loaded = False
            last_err = None

            for enc in encodings:
                try:
                    df = pd.read_csv(
                        full_path, 
                        sep=f_conf["sep"], 
                        index_col=f_conf["index_col"], 
                        encoding=enc, 
                        low_memory=False, 
                        on_bad_lines='skip'
                    )
                    loaded = True
                    break
                except Exception as e:
                    last_err = e

            if loaded:
                note = f_conf.get("note", "")
                inspect_dataframe(df, filename, note)
            else:
                print(f"\nERRORE CRITICO di caricamento per '{filename}': {str(last_err)}")

    print("\n" + "="*80)
    print("ISPEZIONE COMPLETATA CON SUCCESSO!")
    print("================================================================================")
    
    # Close DualWriter log file safely
    sys.stdout.close()

if __name__ == "__main__":
    main()
