import pandas as pd
import numpy as np
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Setup paths
BASE_DIR = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI"
CLEAN_DIR = os.path.join(BASE_DIR, "Clean_Graph_Data")
BENCHMARK_CSV = os.path.join(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi", "benchmark_papers_summary_30.csv")

# Load graph data
n_gene = pd.read_csv(os.path.join(CLEAN_DIR, "node_gene.csv"))
n_variant = pd.read_csv(os.path.join(CLEAN_DIR, "node_variant.csv"))
n_mp = pd.read_csv(os.path.join(CLEAN_DIR, "node_molecular_profile.csv"))
n_evidence = pd.read_csv(os.path.join(CLEAN_DIR, "node_evidence.csv"))
n_drug = pd.read_csv(os.path.join(CLEAN_DIR, "node_drug.csv"))

e_has_variant = pd.read_csv(os.path.join(CLEAN_DIR, "edge_has_variant.csv"))
e_in_mp = pd.read_csv(os.path.join(CLEAN_DIR, "edge_in_molecular_profile.csv"))
e_has_evidence = pd.read_csv(os.path.join(CLEAN_DIR, "edge_has_evidence.csv"))
e_targets_drug = pd.read_csv(os.path.join(CLEAN_DIR, "edge_targets_drug.csv"))
e_has_disease = pd.read_csv(os.path.join(CLEAN_DIR, "civic_evidence_disease_links.csv"))
n_disease = pd.read_csv(os.path.join(CLEAN_DIR, "civic_diseases.csv"))

df_bench = pd.read_csv(BENCHMARK_CSV)

TUMOR_SYNONYMS = {
    "nsclc": ["nsclc", "lung", "non-small cell", "non-small cell lung", "non small cell lung", "adenocarcinoma of lung", "lung adenocarcinoma"],
    "melanoma": ["melanoma", "cutaneous melanoma", "skin melanoma"],
    "breast cancer her2+": ["breast", "mammary", "her2-positive", "her2+", "her2 positive", "erbb2-positive"],
    "breast cancer hr+": ["breast", "mammary", "hormone receptor-positive", "hr+", "hr-positive", "estrogen receptor-positive", "progesterone receptor-positive"],
    "ovarian cancer": ["ovarian", "ovary", "fallopian tube", "peritoneal"],
    "cml": ["leukemia", "myelogenous", "myeloid", "cml", "chronic myeloid", "chronic myelogenous", "chronic granulocytic"],
    "colorectal cancer": ["colorectal", "colon", "rectum", "colonic", "rectal"],
    "gist": ["gist", "gastrointestinal stromal"],
    "aml": ["leukemia", "acute myeloid", "acute myelogenous", "aml", "myeloblast"],
    "solid tumor": ["solid tumor", "solid cancer", "advanced solid", "tumor agnost", "any solid", "cancer", "carcinoma"],
    "gastric cancer": ["gastric", "stomach", "gastroesophageal", "esophageal"],
    "prostate cancer": ["prostate", "prostatic"],
    "cholangiocarcinoma": ["cholangiocarcinoma", "bile duct", "biliary", "cholangiolocellular"],
    "thyroid cancer": ["thyroid", "papillary thyroid", "anaplastic thyroid", "follicular thyroid"]
}

def is_tumor_compatible(bench_tumor, kb_tumor):
    if not bench_tumor or not kb_tumor:
        return False
    bt_clean = bench_tumor.strip().lower()
    kbt_clean = kb_tumor.strip().lower()
    if bt_clean in kbt_clean or kbt_clean in bt_clean:
        return True
    if bt_clean in TUMOR_SYNONYMS:
        syns = TUMOR_SYNONYMS[bt_clean]
        for s in syns:
            if s in kbt_clean or kbt_clean in s:
                return True
    for b_key, syns in TUMOR_SYNONYMS.items():
        if b_key in bt_clean:
            for s in syns:
                if s in kbt_clean:
                    return True
    if bt_clean == "solid tumor" or kbt_clean == "solid tumor":
        return True
    return False

def parse_drug_alternatives(drug_str):
    return [[c.strip() for c in alt.split("+")] for alt in drug_str.strip().split("/")]

def drug_match(name, found_list):
    n = name.upper()
    return any(n in f.upper() or f.upper() in n for f in found_list)

def classify_drugs(expected, found):
    alts = parse_drug_alternatives(expected)
    for alt in alts:
        if all(drug_match(d, found) for d in alt):
            return "✅ COVERED", alt, []
    all_drugs = [d for alt in alts for d in alt]
    matched = [d for d in all_drugs if drug_match(d, found)]
    missing = [d for d in all_drugs if not drug_match(d, found)]
    if matched:
        return "⚠️ PARTIAL", matched, missing
    return "❌ GAP", [], all_drugs

def audit_case(row):
    gene = row["gene"]
    variant = row["variant"]
    tumor = row["tumor"]
    expected = row["expected_drug"]
    
    is_fusion = "Fusion" in str(variant)
    is_biomarker = gene in ("MMR", "TMB") or any(x in str(variant) for x in ("MSI-High", "TMB-High"))
    
    mp_ids = set()
    
    if is_biomarker:
        keyword = "MSI" if "MSI" in str(variant) else "TMB"
        v_hits = n_variant[n_variant["variant_name"].str.upper().str.contains(keyword, na=False)]
        if not v_hits.empty:
            v_ids = set(v_hits["variant_id"])
            mp_ids = set(e_in_mp[e_in_mp["source_variant_id"].isin(v_ids)]["target_molecular_profile_id"])
        if not mp_ids:
            mp_hits = n_mp[n_mp["name"].str.upper().str.contains(keyword, na=False)]
            mp_ids = set(mp_hits["molecular_profile_id"])
    elif is_fusion:
        gene_key = "BCR" if (gene == "ABL1" and "BCR" in variant) else gene.upper()
        mp_hits = n_mp[
            n_mp["name"].str.upper().str.contains(gene_key, na=False) &
            (n_mp["name"].str.upper().str.contains("FUSI", na=False) | n_mp["name"].str.contains("::", na=False) | n_mp["name"].str.upper().str.contains("REARRANG", na=False))
        ]
        mp_ids = set(mp_hits["molecular_profile_id"])
        if not mp_ids:
            g_rows = n_gene[n_gene["hugo_symbol"].str.upper() == gene.upper()]
            if not g_rows.empty:
                e_ids = set(g_rows["entrez_id"])
                v_ids = set(e_has_variant[e_has_variant["source_entrez_id"].isin(e_ids)]["target_variant_id"])
                mp_ids = set(e_in_mp[e_in_mp["source_variant_id"].isin(v_ids)]["target_molecular_profile_id"])
    else:
        g_rows = n_gene[n_gene["hugo_symbol"].str.upper() == gene.upper()]
        if g_rows.empty:
            return "❌ GAP", [], "Nessun gene", "—", "—"
        e_ids = set(g_rows["entrez_id"])
        all_v_ids = set(e_has_variant[e_has_variant["source_entrez_id"].isin(e_ids)]["target_variant_id"])
        
        if variant.lower() in ("mutation", "amplification"):
            v_ids = all_v_ids
        else:
            tokens = re.split(r'\s+', variant.upper())
            key = next((t for t in tokens if re.match(r'[A-Z]\d+[A-Z]?|EX|ITD|DEL|INS|R\d+', t)), tokens[0])
            v_hits = n_variant[n_variant["variant_id"].isin(all_v_ids) & n_variant["variant_name"].str.upper().str.contains(key, na=False)]
            if v_hits.empty and len(tokens) > 1:
                key2 = next((t for t in tokens if t.isdigit()), None)
                if key2:
                    v_hits = n_variant[n_variant["variant_id"].isin(all_v_ids) & n_variant["variant_name"].str.upper().str.contains(key2, na=False)]
            if v_hits.empty:
                v_ids = all_v_ids
            else:
                v_ids = set(v_hits["variant_id"])
        mp_ids = set(e_in_mp[e_in_mp["source_variant_id"].isin(v_ids)]["target_molecular_profile_id"])

    # Traverse to Evidence & Drugs
    evs_df = e_has_evidence[e_has_evidence["source_molecular_profile_id"].isin(mp_ids)]
    ev_ids = set(evs_df["target_evidence_id"])
    
    pred_evs = n_evidence[
        n_evidence["evidence_id"].isin(ev_ids) &
        (n_evidence["evidence_type"] == "Predictive") &
        (n_evidence["significance"].str.contains("Sensitivity|Response", case=False, na=False))
    ]
    
    if pred_evs.empty:
        return "❌ GAP", [], "Nessuna evidenza predittiva di sensibilità", "—", "—"

    # Separate CIViC and OncoKB evidences
    civic_evs = pred_evs[pred_evs["source_type"] != "OncoKB"]
    oncokb_evs = pred_evs[pred_evs["source_type"] == "OncoKB"]
    
    # Check coverage on both sources
    def get_source_data(sub_evs):
        if sub_evs.empty:
            return [], []
        t_match = sub_evs[sub_evs["disease"].apply(lambda d: is_tumor_compatible(tumor, d) if pd.notna(d) else False)]
        final_evs = t_match if not t_match.empty else sub_evs
        final_ev_ids = set(final_evs["evidence_id"])
        drug_ids = set(e_targets_drug[e_targets_drug["source_evidence_id"].isin(final_ev_ids)]["target_drug_concept_id"])
        drugs = n_drug[n_drug["concept_id"].isin(drug_ids)]["drug_name"].tolist()
        return drugs, t_match.empty
        
    civic_drugs, civic_mismatch = get_source_data(civic_evs)
    oncokb_drugs, oncokb_mismatch = get_source_data(oncokb_evs)
    
    # Combine found drugs
    all_found_drugs = list(set(civic_drugs + oncokb_drugs))
    
    # Classify expected drug against all found drugs
    status, matched, missing = classify_drugs(expected, all_found_drugs)
    
    # Mismatch declass
    has_civic_compat = len(civic_drugs) > 0 and not civic_mismatch
    has_okb_compat = len(oncokb_drugs) > 0 and not oncokb_mismatch
    
    if status == "✅ COVERED":
        # Check if the matched alternative was compatible or mismatched in disease
        alts = parse_drug_alternatives(expected)
        matched_alt = None
        for alt in alts:
            if all(drug_match(d, all_found_drugs) for d in alt):
                matched_alt = alt
                break
        
        # Check compatibility for the matched alternative
        civic_ok = all(drug_match(d, civic_drugs) for d in matched_alt) if matched_alt else False
        oncokb_ok = all(drug_match(d, oncokb_drugs) for d in matched_alt) if matched_alt else False
        
        is_civic_valid = civic_ok and not civic_mismatch
        is_oncokb_valid = oncokb_ok and not oncokb_mismatch
        
        if not is_civic_valid and not is_oncokb_valid:
            status = "⚠️ PARTIAL"
            notes = "mismatch tumore per tutti i match"
        else:
            notes = "compatibile"
    else:
        notes = f"mancanti: {missing}"
        
    # Source attribution
    sources = []
    if any(drug_match(d, civic_drugs) for d in all_found_drugs):
        sources.append("CIViC")
    if any(drug_match(d, oncokb_drugs) for d in all_found_drugs):
        sources.append("OncoKB")
    source_str = " + ".join(sources) if sources else "Nessuna"
    
    return status, expected, all_found_drugs, source_str, notes

if __name__ == "__main__":
    results = []
    for _, row in df_bench.iterrows():
        status, expected, found, source, notes = audit_case(row)
        results.append({
            "case_id": row["case_id"],
            "gene": row["gene"],
            "variant": row["variant"],
            "tumor": row["tumor"],
            "expected": expected,
            "status": status,
            "found": found,
            "source": source,
            "notes": notes
        })
    df_res = pd.DataFrame(results)
    
    print("\n=== CASI NON COVERED (PARTIAL O GAP) ===")
    not_cov = df_res[df_res["status"] != "✅ COVERED"]
    print(not_cov[["case_id", "gene", "variant", "tumor", "expected", "status", "source", "notes"]].to_string(index=False))
    
    print("\n=== STATISTICHE COPERTURA FONTI ===")
    print(df_res["source"].value_counts())
    
    print("\n=== STATISTICHE STATO GENERALE ===")
    print(df_res["status"].value_counts())
