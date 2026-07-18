import os
import sys
import re
import pandas as pd
import numpy as np

# Open output log file inside Python to avoid Windows PowerShell redirection quirks
log_file_path = 'etl_pipeline_log.txt'
sys.stdout = open(log_file_path, 'w', encoding='utf-8')

print("============================================================")
print("ONCOLOGICAL KNOWLEDGE GRAPH ETL PIPELINE")
print("============================================================")

# Paths
BASE_DIR = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI"
OUT_DIR = os.path.join(BASE_DIR, "Clean_Graph_Data")
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Sorgenti dati: {BASE_DIR}")
print(f"Directory di output puliti: {OUT_DIR}\n")

# Helper for string cleanup and normalization
def normalize_name(name):
    if pd.isna(name):
        return ""
    # Normalize uppercase, remove spaces and standard punctuation
    val = str(name).upper().strip()
    # Replace common commercial tags
    val = re.sub(r'\b(HYDROCHLORIDE|SULFATE|TARTRATE|CITRATE|MALEATE|PHOSPHATE)\b', '', val)
    val = re.sub(r'[^A-Z0-9]', '', val)
    return val

# Load all files
print("Caricamento dataset in corso...")

# 1. Cancer Gene List
df_cancer_genes = pd.read_csv(os.path.join(BASE_DIR, "cancerGeneList.tsv"), sep='\t', encoding='utf-8')
print(f"  cancerGeneList.tsv caricato: {len(df_cancer_genes)} righe")

# 2. Feature Summaries
df_features = pd.read_csv(os.path.join(BASE_DIR, "Civic", "01-May-2026-FeatureSummaries.tsv"), sep='\t', encoding='utf-8')
print(f"  FeatureSummaries.tsv caricato: {len(df_features)} righe")

# 3. Variant Summaries (Corrected loading with index_col=False)
df_variants = pd.read_csv(os.path.join(BASE_DIR, "Civic", "01-May-2026-VariantSummaries.tsv"), sep='\t', index_col=False, encoding='utf-8')
print(f"  VariantSummaries.tsv caricato (CORRETTO): {len(df_variants)} righe")

# 4. Molecular Profile Summaries
df_mol_profiles = pd.read_csv(os.path.join(BASE_DIR, "Civic", "01-May-2026-MolecularProfileSummaries.tsv"), sep='\t', encoding='utf-8')
print(f"  MolecularProfileSummaries.tsv caricato: {len(df_mol_profiles)} righe")

# 5. Accepted Clinical Evidence Summaries
df_evidence = pd.read_csv(os.path.join(BASE_DIR, "Civic", "01-May-2026-AcceptedClinicalEvidenceSummaries.tsv"), sep='\t', encoding='utf-8')
print(f"  AcceptedClinicalEvidenceSummaries.tsv caricato: {len(df_evidence)} righe")

# 6. DGIdb Categories
df_dgidb_categories = pd.read_csv(os.path.join(BASE_DIR, "DGIdb", "categories.tsv"), sep='\t', encoding='utf-8')
print(f"  DGIdb categories.tsv caricato: {len(df_dgidb_categories)} righe")

# 7. DGIdb Drugs
df_dgidb_drugs = pd.read_csv(os.path.join(BASE_DIR, "DGIdb", "drugs.tsv"), sep='\t', encoding='utf-8')
print(f"  DGIdb drugs.tsv caricato: {len(df_dgidb_drugs)} righe")

# 8. DGIdb Genes
df_dgidb_genes = pd.read_csv(os.path.join(BASE_DIR, "DGIdb", "genes.tsv"), sep='\t', encoding='utf-8')
print(f"  DGIdb genes.tsv caricato: {len(df_dgidb_genes)} righe")

# 9. DGIdb Interactions
df_dgidb_interactions = pd.read_csv(os.path.join(BASE_DIR, "DGIdb", "interactions.tsv"), sep='\t', encoding='utf-8')
print(f"  DGIdb interactions.tsv caricato: {len(df_dgidb_interactions)} righe")

# 10. Companion Diagnostic Devices
df_companion = pd.read_csv(os.path.join(BASE_DIR, "companion_diagnostic_devices.tsv"), sep='\t', encoding='utf-8')
print(f"  companion_diagnostic_devices.tsv caricato: {len(df_companion)} righe")

# 11. FDA Oncology Therapies XLSX
xlsx_path = os.path.join(BASE_DIR, "fda_approved_oncology_therapies.xlsx")
df_fda_xlsx = pd.read_excel(xlsx_path, sheet_name="FDA-Approved Oncology Therapies")
print(f"  fda_approved_oncology_therapies.xlsx (FDA sheet) caricato: {len(df_fda_xlsx)} righe\n")


# ------------------------------------------------------------
# STEP 1: NODI - DRUG
# ------------------------------------------------------------
print("--- ELABORAZIONE NODI: DRUG ---")
# Deduplicate DGIdb drugs on concept_id, discarding nulls
df_drugs_clean = df_dgidb_drugs.dropna(subset=['concept_id']).copy()
# Remove duplicate concept_ids (keep the first record)
df_drugs_clean = df_drugs_clean.drop_duplicates(subset=['concept_id']).copy()

# Map and clean fields
df_drugs_clean['drug_name'] = df_drugs_clean['drug_name'].astype(str).str.upper().str.strip()
df_drugs_clean['approved'] = df_drugs_clean['approved'].map({'True': True, 'False': False, True: True, False: False})
df_drugs_clean['immunotherapy'] = df_drugs_clean['immunotherapy'].map({'True': True, 'False': False, True: True, False: False})
df_drugs_clean['anti_neoplastic'] = df_drugs_clean['anti_neoplastic'].map({'True': True, 'False': False, True: True, False: False})

# Build dictionary for quick name-to-concept_id lookups
drug_name_map = {}
for _, row in df_drugs_clean.iterrows():
    # Primary index on normalized drug name
    norm_c = normalize_name(row['drug_name'])
    if norm_c:
        drug_name_map[norm_c] = row['concept_id']
    # Also index on claim name
    norm_claim = normalize_name(row['drug_claim_name'])
    if norm_claim:
        drug_name_map[norm_claim] = row['concept_id']

# Process FDA approved oncology therapies sheet
# Keep only precision oncology therapies (Precision oncology therapy == 'Y')
df_fda_filtered = df_fda_xlsx[df_fda_xlsx['Precision oncology therapy'] == 'Y'].copy()
print(f"  FDA Oncology Precision Therapies (Y): {len(df_fda_filtered)}")

fda_drugs_list = []
for _, row in df_fda_filtered.iterrows():
    raw_name = str(row['FDA-approved drug(s) a']).strip()
    norm_name = normalize_name(raw_name)
    
    biomarker = str(row['FDA drug label listed biomarker(s) b']).strip() if not pd.isna(row['FDA drug label listed biomarker(s) b']) else ""
    drug_class = str(row['Class of agent(s) c']).strip() if not pd.isna(row['Class of agent(s) c']) else ""
    mechanism = str(row['Mechanism of action or drug target c']).strip() if not pd.isna(row['Mechanism of action or drug target c']) else ""
    
    # Try parsing approval year
    raw_year = str(row['Year of drug’s first FDA- approval']).strip()
    approval_year = ""
    match_year = re.search(r'\d{4}', raw_year)
    if match_year:
        approval_year = int(match_year.group(0))
        
    # Check if this drug exists in DGIdb drug map
    if norm_name in drug_name_map:
        cid = drug_name_map[norm_name]
        # Enrich the existing drug row
        df_drugs_clean.loc[df_drugs_clean['concept_id'] == cid, 'fda_approval_year'] = approval_year
        df_drugs_clean.loc[df_drugs_clean['concept_id'] == cid, 'biomarker'] = biomarker
        df_drugs_clean.loc[df_drugs_clean['concept_id'] == cid, 'drug_class'] = drug_class
        df_drugs_clean.loc[df_drugs_clean['concept_id'] == cid, 'mechanism'] = mechanism
    else:
        # Create a new FDA drug record
        cid = f"fda:{norm_name}"
        fda_drugs_list.append({
            'concept_id': cid,
            'drug_claim_name': raw_name,
            'nomenclature': 'FDA Precision Oncology',
            'drug_name': raw_name.upper(),
            'approved': True,
            'immunotherapy': False,
            'anti_neoplastic': True,
            'source_db_name': 'FDA_Oncology_Therapies',
            'source_db_version': '2023-07-25',
            'fda_approval_year': approval_year,
            'biomarker': biomarker,
            'drug_class': drug_class,
            'mechanism': mechanism
        })
        # Add to lookup map
        drug_name_map[norm_name] = cid

# Append new FDA drugs to general drug dataframe
if fda_drugs_list:
    df_drugs_final = pd.concat([df_drugs_clean, pd.DataFrame(fda_drugs_list)], ignore_index=True)
else:
    df_drugs_final = df_drugs_clean.copy()

# Add placeholder columns if not already filled
for col in ['fda_approval_year', 'biomarker', 'drug_class', 'mechanism']:
    if col not in df_drugs_final.columns:
        df_drugs_final[col] = None

# Save Node: Drug
drug_node_path = os.path.join(OUT_DIR, "node_drug.csv")
df_drugs_final.to_csv(drug_node_path, index=False, encoding='utf-8')
print(f"  Nodi Drug salvati: {len(df_drugs_final)} in {drug_node_path}")


# ------------------------------------------------------------
# STEP 2: NODI - GENE
# ------------------------------------------------------------
print("\n--- ELABORAZIONE NODI: GENE ---")
# 1. Parse categories mapping from categories.tsv
categories_map = {}
for _, row in df_dgidb_categories.iterrows():
    gname = str(row['name']).strip().upper()
    cat = str(row['name-2']).strip()
    if gname not in categories_map:
        categories_map[gname] = []
    if cat not in categories_map[gname]:
        categories_map[gname].append(cat)

# 2. Process primary cancerGeneList.tsv
# Standardize Entrez ID to integer
df_cancer_genes['Entrez Gene ID'] = df_cancer_genes['Entrez Gene ID'].astype(int)
df_cancer_genes_unique = df_cancer_genes.drop_duplicates(subset=['Entrez Gene ID']).copy()

genes_list = []
entrez_seen = set()

for _, row in df_cancer_genes_unique.iterrows():
    entrez_id = int(row['Entrez Gene ID'])
    hugo_symbol = str(row['Hugo Symbol']).strip()
    
    # Parse aliases
    aliases_raw = str(row['Gene Aliases']) if not pd.isna(row['Gene Aliases']) else ""
    aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()]
    
    gene_type = str(row['Gene Type']).strip() if not pd.isna(row['Gene Type']) else ""
    is_oncokb = True if str(row['OncoKB Annotated']).strip() == 'Yes' else False
    grch38_isoform = str(row['GRCh38 Isoform']).strip() if not pd.isna(row['GRCh38 Isoform']) else ""
    grch38_refseq = str(row['GRCh38 RefSeq']).strip() if not pd.isna(row['GRCh38 RefSeq']) else ""
    
    # Check if there are DGIdb categories for this gene
    g_categories = categories_map.get(hugo_symbol.upper(), [])
    categories_str = ";".join(g_categories) # Semi-colon separated list
    
    genes_list.append({
        'entrez_id': entrez_id,
        'hugo_symbol': hugo_symbol,
        'gene_type': gene_type,
        'is_oncokb_annotated': is_oncokb,
        'grch38_isoform': grch38_isoform,
        'grch38_refseq': grch38_refseq,
        'aliases': ";".join(aliases),
        'categories': categories_str,
        'civic_description': ""
    })
    entrez_seen.add(entrez_id)

# 3. Pull additional Gene nodes from Civic FeatureSummaries (feature_type == 'Gene')
# and merge description if entrez_id already exists, otherwise add as new node!
df_features_genes = df_features[df_features['feature_type'] == 'Gene'].copy()
df_features_genes = df_features_genes.dropna(subset=['entrez_id']).copy()

# Cast entrez_id to int in FeatureSummaries
df_features_genes['entrez_id'] = df_features_genes['entrez_id'].astype(int)

new_civic_genes_count = 0
for _, row in df_features_genes.iterrows():
    entrez_id = int(row['entrez_id'])
    civic_desc = str(row['description']).strip() if not pd.isna(row['description']) else ""
    hugo_symbol = str(row['name']).strip()
    
    # If gene already exists, enrich description
    found = False
    for g in genes_list:
        if g['entrez_id'] == entrez_id:
            g['civic_description'] = civic_desc
            found = True
            break
            
    if not found and entrez_id not in entrez_seen:
        # Pull categories for this gene symbol
        g_categories = categories_map.get(hugo_symbol.upper(), [])
        categories_str = ";".join(g_categories)
        
        aliases_raw = str(row['feature_aliases']) if not pd.isna(row['feature_aliases']) else ""
        aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()]
        
        genes_list.append({
            'entrez_id': entrez_id,
            'hugo_symbol': hugo_symbol,
            'gene_type': 'UNCATEGORIZED',
            'is_oncokb_annotated': False,
            'grch38_isoform': "",
            'grch38_refseq': "",
            'aliases': ";".join(aliases),
            'categories': categories_str,
            'civic_description': civic_desc
        })
        entrez_seen.add(entrez_id)
        new_civic_genes_count += 1

print(f"  Geni importati da cancerGeneList: {len(df_cancer_genes_unique)}")
print(f"  Geni aggiuntivi rilevati da Civic FeatureSummaries: {new_civic_genes_count}")

# Save Node: Gene
df_genes_final = pd.DataFrame(genes_list)
gene_node_path = os.path.join(OUT_DIR, "node_gene.csv")
df_genes_final.to_csv(gene_node_path, index=False, encoding='utf-8')
print(f"  Nodi Gene salvati: {len(df_genes_final)} in {gene_node_path}")


# ------------------------------------------------------------
# STEP 3: NODI - VARIANT
# ------------------------------------------------------------
print("\n--- ELABORAZIONE NODI: VARIANT ---")
# We process df_variants (already loaded using index_col=False)
variants_list = []
for _, row in df_variants.iterrows():
    # Fallback to parse ID from URL in case of any index shift issues, 
    # but index_col=False has loaded variant_id as int64.
    variant_id = row['variant_id']
    if not isinstance(variant_id, (int, np.integer)):
        # Extract via regex from URL
        match_url = re.search(r'/variants/(\d+)', str(row['variant_civic_url']))
        if match_url:
            variant_id = int(match_url.group(1))
        else:
            continue
            
    variant_name = str(row['variant']).strip() if not pd.isna(row['variant']) else ""
    f_type = str(row['feature_type']).strip() if not pd.isna(row['feature_type']) else ""
    
    # Parse HGVS descriptions list
    hgvs_raw = str(row['hgvs_descriptions']) if not pd.isna(row['hgvs_descriptions']) else ""
    hgvs = [h.strip() for h in hgvs_raw.split(',') if h.strip()]
    
    chromosome = str(row['chromosome']).strip() if not pd.isna(row['chromosome']) else ""
    start = int(row['start']) if not pd.isna(row['start']) else ""
    stop = int(row['stop']) if not pd.isna(row['stop']) else ""
    ref_bases = str(row['reference_bases']).strip() if not pd.isna(row['reference_bases']) else ""
    var_bases = str(row['variant_bases']).strip() if not pd.isna(row['variant_bases']) else ""
    
    variant_types = str(row['variant_types']).strip() if not pd.isna(row['variant_types']) else ""
    allele_registry_id = str(row['allele_registry_id']).strip() if not pd.isna(row['allele_registry_id']) else ""
    civic_url = str(row['variant_civic_url']).strip() if not pd.isna(row['variant_civic_url']) else ""
    
    variants_list.append({
        'variant_id': int(variant_id),
        'variant_name': variant_name,
        'feature_type': f_type,
        'hgvs_descriptions': ";".join(hgvs),
        'chromosome': chromosome,
        'start': start,
        'stop': stop,
        'reference_bases': ref_bases,
        'variant_bases': var_bases,
        'variant_types': variant_types,
        'allele_registry_id': allele_registry_id,
        'civic_url': civic_url
    })

# Save Node: Variant
df_variants_final = pd.DataFrame(variants_list)
# Remove duplicate variant_ids if any
df_variants_final = df_variants_final.drop_duplicates(subset=['variant_id']).copy()
variant_node_path = os.path.join(OUT_DIR, "node_variant.csv")
df_variants_final.to_csv(variant_node_path, index=False, encoding='utf-8')
print(f"  Nodi Variant salvati: {len(df_variants_final)} in {variant_node_path}")


# ------------------------------------------------------------
# STEP 4: NODI - MOLECULAR PROFILE
# ------------------------------------------------------------
print("\n--- ELABORAZIONE NODI: MOLECULAR PROFILE ---")
mol_profiles_list = []
for _, row in df_mol_profiles.iterrows():
    mp_id = int(row['molecular_profile_id'])
    mp_name = str(row['name']).strip()
    summary = str(row['summary']).strip() if not pd.isna(row['summary']) else ""
    score = float(row['evidence_score']) if not pd.isna(row['evidence_score']) else 0.0
    
    # Parse aliases
    aliases_raw = str(row['aliases']) if not pd.isna(row['aliases']) else ""
    aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()]
    
    mol_profiles_list.append({
        'molecular_profile_id': mp_id,
        'name': mp_name,
        'summary': summary,
        'evidence_score': score,
        'aliases': ";".join(aliases)
    })

# Save Node: MolecularProfile
df_mol_profiles_final = pd.DataFrame(mol_profiles_list)
df_mol_profiles_final = df_mol_profiles_final.drop_duplicates(subset=['molecular_profile_id']).copy()
mp_node_path = os.path.join(OUT_DIR, "node_molecular_profile.csv")
df_mol_profiles_final.to_csv(mp_node_path, index=False, encoding='utf-8')
print(f"  Nodi MolecularProfile salvati: {len(df_mol_profiles_final)} in {mp_node_path}")


# ------------------------------------------------------------
# STEP 5: NODI - EVIDENCE
# ------------------------------------------------------------
print("\n--- ELABORAZIONE NODI: EVIDENCE ---")
evidence_list = []
for _, row in df_evidence.iterrows():
    ev_id = int(row['evidence_id'])
    ev_type = str(row['evidence_type']).strip()
    ev_level = str(row['evidence_level']).strip()
    ev_dir = str(row['evidence_direction']).strip() if not pd.isna(row['evidence_direction']) else ""
    significance = str(row['significance']).strip() if not pd.isna(row['significance']) else ""
    statement = str(row['evidence_statement']).strip()
    
    # CITATION IDs (PMIDs, split out if multiple)
    citation_id_raw = str(row['citation_id']).strip()
    citations = [c.strip() for c in citation_id_raw.split(',') if c.strip()]
    
    source_type = str(row['source_type']).strip()
    rating = int(row['rating']) if not pd.isna(row['rating']) else ""
    var_origin = str(row['variant_origin']).strip() if not pd.isna(row['variant_origin']) else ""
    disease = str(row['disease']).strip() if not pd.isna(row['disease']) else ""
    
    doid = ""
    if not pd.isna(row['doid']):
        doid = str(int(row['doid']))
        
    evidence_list.append({
        'evidence_id': ev_id,
        'evidence_type': ev_type,
        'evidence_level': ev_level,
        'evidence_direction': ev_dir,
        'significance': significance,
        'evidence_statement': statement,
        'citation_id': ";".join(citations),
        'source_type': source_type,
        'rating': rating,
        'variant_origin': var_origin,
        'disease': disease,
        'doid': doid
    })

# Save Node: Evidence
df_evidence_final = pd.DataFrame(evidence_list)
df_evidence_final = df_evidence_final.drop_duplicates(subset=['evidence_id']).copy()
evidence_node_path = os.path.join(OUT_DIR, "node_evidence.csv")
df_evidence_final.to_csv(evidence_node_path, index=False, encoding='utf-8')
print(f"  Nodi Evidence salvati: {len(df_evidence_final)} in {evidence_node_path}")


# ------------------------------------------------------------
# STEP 6: NODI - COMPANION DIAGNOSTIC
# ------------------------------------------------------------
print("\n--- ELABORAZIONE NODI: COMPANION DIAGNOSTIC ---")
companion_list = []
comp_id_seen = set()

for idx, row in df_companion.iterrows():
    device_name = str(row['Companion Diagnostic Device']).strip()
    platform = str(row['Platform Type']).strip()
    
    # Specimen types (comma separated lists)
    specimens_raw = str(row['Specimen Types(s)']).strip()
    specimens = [s.strip() for s in specimens_raw.split(',') if s.strip()]
    
    gene_symbol = str(row['Gene']).strip()
    raw_drug = str(row['Drug(s)']).strip()
    
    # Generate unique slug for compound key
    device_slug = normalize_name(device_name)[:15]
    gene_slug = normalize_name(gene_symbol)
    drug_slug = normalize_name(raw_drug)[:15]
    device_id = f"cdx:{device_slug}:{gene_slug}:{drug_slug}"
    
    if device_id not in comp_id_seen:
        companion_list.append({
            'device_id': device_id,
            'device_name': device_name,
            'platform_type': platform,
            'specimen_types': ";".join(specimens),
            'gene': gene_symbol,
            'drug': raw_drug
        })
        comp_id_seen.add(device_id)

# Save Node: CompanionDiagnostic
df_companion_final = pd.DataFrame(companion_list)
companion_node_path = os.path.join(OUT_DIR, "node_companion_diagnostic.csv")
df_companion_final.to_csv(companion_node_path, index=False, encoding='utf-8')
print(f"  Nodi CompanionDiagnostic salvati: {len(df_companion_final)} in {companion_node_path}")


# ============================================================
# STEP 7: ARCHI (RELATIONSHIPS)
# ============================================================
print("\n" + "="*40)
print("ARCHI (RELATIONSHIPS) GENERATION")
print("="*40)

# ------------------------------------------------------------
# STEP 7.1: (:Gene)-[:HAS_VARIANT]->(:Variant)
# ------------------------------------------------------------
print("\n--- ELABORAZIONE ARCO: (:Gene)-[:HAS_VARIANT]->(:Variant) ---")
# Relate VariantSummaries on feature_id to FeatureSummaries on feature_id to retrieve entrez_id.
# If matched and entrez_id exists, write relation to Variant.variant_id.
df_feature_entrez = df_features[['feature_id', 'entrez_id', 'feature_type']].dropna(subset=['entrez_id']).copy()
df_feature_entrez['entrez_id'] = df_feature_entrez['entrez_id'].astype(int)

# Create a mapping feature_id -> entrez_id
feature_entrez_map = dict(zip(df_feature_entrez['feature_id'], df_feature_entrez['entrez_id']))

gene_variant_edges = []
for _, row in df_variants_final.iterrows():
    vid = row['variant_id']
    # Look up raw variant feature_id in VariantSummaries table
    raw_feature_id = df_variants.loc[df_variants['variant_id'] == vid, 'feature_id'].iloc[0]
    
    if raw_feature_id in feature_entrez_map:
        entrez = feature_entrez_map[raw_feature_id]
        if entrez in entrez_seen:
            gene_variant_edges.append({
                'source_entrez_id': int(entrez),
                'target_variant_id': int(vid)
            })

df_edge_has_variant = pd.DataFrame(gene_variant_edges)
has_variant_path = os.path.join(OUT_DIR, "edge_has_variant.csv")
df_edge_has_variant.to_csv(has_variant_path, index=False, encoding='utf-8')
print(f"  Archi HAS_VARIANT salvati: {len(df_edge_has_variant)} in {has_variant_path}")


# ------------------------------------------------------------
# STEP 7.2: (:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
# ------------------------------------------------------------
print("\n--- ELABORAZIONE ARCO: (:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile) ---")
# Explode MolecularProfileSummaries.variant_ids (split by ", ")
mp_variant_edges = []
for _, row in df_mol_profiles_final.iterrows():
    mp_id = row['molecular_profile_id']
    raw_vids = df_mol_profiles.loc[df_mol_profiles['molecular_profile_id'] == mp_id, 'variant_ids'].iloc[0]
    
    if not pd.isna(raw_vids):
        vids_list = [v.strip() for v in str(raw_vids).split(',') if v.strip()]
        for v in vids_list:
            try:
                vid = int(float(v))
                if vid in df_variants_final['variant_id'].values:
                    mp_variant_edges.append({
                        'source_variant_id': vid,
                        'target_molecular_profile_id': mp_id
                    })
            except Exception:
                pass

df_edge_in_mp = pd.DataFrame(mp_variant_edges)
in_mp_path = os.path.join(OUT_DIR, "edge_in_molecular_profile.csv")
df_edge_in_mp.to_csv(in_mp_path, index=False, encoding='utf-8')
print(f"  Archi IN_MOLECULAR_PROFILE salvati: {len(df_edge_in_mp)} in {in_mp_path}")


# ------------------------------------------------------------
# STEP 7.3: (:MolecularProfile)-[:HAS_EVIDENCE]->(:Evidence)
# ------------------------------------------------------------
print("\n--- ELABORAZIONE ARCO: (:MolecularProfile)-[:HAS_EVIDENCE]->(:Evidence) ---")
mp_evidence_edges = []
for _, row in df_evidence_final.iterrows():
    ev_id = row['evidence_id']
    raw_mp_id = df_evidence.loc[df_evidence['evidence_id'] == ev_id, 'molecular_profile_id'].iloc[0]
    
    if not pd.isna(raw_mp_id):
        mp_id = int(raw_mp_id)
        if mp_id in df_mol_profiles_final['molecular_profile_id'].values:
            mp_evidence_edges.append({
                'source_molecular_profile_id': mp_id,
                'target_evidence_id': ev_id
            })

df_edge_has_evidence = pd.DataFrame(mp_evidence_edges)
has_evidence_path = os.path.join(OUT_DIR, "edge_has_evidence.csv")
df_edge_has_evidence.to_csv(has_evidence_path, index=False, encoding='utf-8')
print(f"  Archi HAS_EVIDENCE salvati: {len(df_edge_has_evidence)} in {has_evidence_path}")


# ------------------------------------------------------------
# STEP 7.4: (:Evidence)-[:TARGETS_DRUG]->(:Drug)
# ------------------------------------------------------------
print("\n--- ELABORAZIONE ARCO: (:Evidence)-[:TARGETS_DRUG]->(:Drug) ---")
# Match therapies split on commas against drugs. Log failures in fuzzy_match_failures.log
evidence_drug_edges = []
fuzzy_failures = []

for _, row in df_evidence_final.iterrows():
    ev_id = row['evidence_id']
    raw_therapies = df_evidence.loc[df_evidence['evidence_id'] == ev_id, 'therapies'].iloc[0]
    
    # Edge properties
    level = row['evidence_level']
    sig = row['significance']
    direction = row['evidence_direction']
    
    if not pd.isna(raw_therapies):
        therapies_list = [t.strip() for t in str(raw_therapies).split(',') if t.strip()]
        for t in therapies_list:
            norm_t = normalize_name(t)
            if norm_t in drug_name_map:
                cid = drug_name_map[norm_t]
                evidence_drug_edges.append({
                    'source_evidence_id': ev_id,
                    'target_drug_concept_id': cid,
                    'evidence_level': level,
                    'significance': sig,
                    'evidence_direction': direction
                })
            else:
                fuzzy_failures.append({
                    'context': 'Evidence Therapies Ingestion',
                    'evidence_id': ev_id,
                    'unmatched_string': t,
                    'normalized': norm_t
                })

df_edge_targets_drug = pd.DataFrame(evidence_drug_edges)
targets_drug_path = os.path.join(OUT_DIR, "edge_targets_drug.csv")
df_edge_targets_drug.to_csv(targets_drug_path, index=False, encoding='utf-8')
print(f"  Archi TARGETS_DRUG salvati: {len(df_edge_targets_drug)} in {targets_drug_path}")


# ------------------------------------------------------------
# STEP 7.5: (:Gene)-[:INTERACTS_WITH]->(:Drug) (DGIdb Interactions)
# ------------------------------------------------------------
print("\n--- ELABORAZIONE ARCO: (:Gene)-[:INTERACTS_WITH]->(:Drug) ---")
# Keep neoplastic interactions OR oncology genes in cancerGeneList.
# Map gene_name in interactions to Hugo Symbol in node_gene to get entrez_id.
# Map drug_concept_id directly to concept_id in node_drug.
gene_symbol_to_entrez = dict(zip(df_genes_final['hugo_symbol'].str.upper(), df_genes_final['entrez_id']))

# Map drug concept IDs to verify existence
drug_concepts_exist = set(df_drugs_final['concept_id'])

# Also create list of anti_neoplastic drug concept ids
anti_neoplastic_drug_concepts = set(df_drugs_final[df_drugs_final['anti_neoplastic'] == True]['concept_id'])

interaction_edges = []
for _, row in df_dgidb_interactions.iterrows():
    gene_symbol = str(row['gene_name']).strip().upper()
    drug_concept_id = str(row['drug_concept_id']).strip()
    
    # 1. Filter: anti_neoplastic drug OR oncology gene present
    is_gene_oncology = gene_symbol in gene_symbol_to_entrez
    is_drug_neoplastic = drug_concept_id in anti_neoplastic_drug_concepts
    
    if is_gene_oncology or is_drug_neoplastic:
        # Check if mapped concept IDs exist in our Nodes
        if is_gene_oncology and (drug_concept_id in drug_concepts_exist):
            entrez = gene_symbol_to_entrez[gene_symbol]
            
            # Map edge attributes
            int_type = str(row['interaction_type']).strip() if not pd.isna(row['interaction_type']) else "unknown"
            score = float(row['interaction_score']) if not pd.isna(row['interaction_score']) else 0.0
            source_db = str(row['interaction_source_db_name']).strip()
            
            interaction_edges.append({
                'source_gene_entrez_id': int(entrez),
                'target_drug_concept_id': drug_concept_id,
                'interaction_type': int_type,
                'interaction_score': score,
                'source_db': source_db
            })

df_edge_interacts_with = pd.DataFrame(interaction_edges)
# Drop duplicates to keep clean edges
df_edge_interacts_with = df_edge_interacts_with.drop_duplicates(subset=['source_gene_entrez_id', 'target_drug_concept_id', 'interaction_type', 'source_db']).copy()
interacts_path = os.path.join(OUT_DIR, "edge_interacts_with.csv")
df_edge_interacts_with.to_csv(interacts_path, index=False, encoding='utf-8')
print(f"  Archi INTERACTS_WITH salvati: {len(df_edge_interacts_with)} in {interacts_path}")


# ------------------------------------------------------------
# STEP 7.6: (:Drug)-[:HAS_COMPANION_DIAGNOSTIC]->(:CompanionDiagnostic)
# ------------------------------------------------------------
print("\n--- ELABORAZIONE ARCO: (:Drug)-[:HAS_COMPANION_DIAGNOSTIC]->(:CompanionDiagnostic) ---")
cdx_drug_edges = []
cdx_gene_edges = []

for _, row in df_companion_final.iterrows():
    device_id = row['device_id']
    raw_drugs = row['drug']
    raw_gene = row['gene']
    
    # 1. Mappatura con Drug (con split su virgola)
    drugs_list = [d.strip() for d in raw_drugs.split(',') if d.strip()]
    for d in drugs_list:
        norm_d = normalize_name(d)
        if norm_d in drug_name_map:
            cid = drug_name_map[norm_d]
            cdx_drug_edges.append({
                'source_drug_concept_id': cid,
                'target_device_id': device_id
            })
        else:
            fuzzy_failures.append({
                'context': 'Companion Diagnostic Drug Ingestion',
                'device_id': device_id,
                'unmatched_string': d,
                'normalized': norm_d
            })
            
    # 2. Mappatura con Gene (diretto con simbolo)
    norm_g = raw_gene.strip().upper()
    if norm_g in gene_symbol_to_entrez:
        entrez = gene_symbol_to_entrez[norm_g]
        cdx_gene_edges.append({
            'source_device_id': device_id,
            'target_gene_entrez_id': int(entrez)
        })

df_edge_has_cdx = pd.DataFrame(cdx_drug_edges)
has_cdx_path = os.path.join(OUT_DIR, "edge_has_companion_diagnostic.csv")
df_edge_has_cdx.to_csv(has_cdx_path, index=False, encoding='utf-8')
print(f"  Archi HAS_COMPANION_DIAGNOSTIC salvati: {len(df_edge_has_cdx)} in {has_cdx_path}")

df_edge_diagnoses_gene = pd.DataFrame(cdx_gene_edges)
diagnoses_gene_path = os.path.join(OUT_DIR, "edge_diagnoses_gene.csv")
df_edge_diagnoses_gene.to_csv(diagnoses_gene_path, index=False, encoding='utf-8')
print(f"  Archi DIAGNOSES_GENE salvati: {len(df_edge_diagnoses_gene)} in {diagnoses_gene_path}")


# ------------------------------------------------------------
# STEP 8: WRITE FUZZY MATCH FAILURES LOG
# ------------------------------------------------------------
print("\n" + "="*40)
print("FUZZY MATCH FAILURES AND COMPILATION LOG")
print("="*40)

df_failures = pd.DataFrame(fuzzy_failures)
failures_log_path = os.path.join(OUT_DIR, "fuzzy_match_failures.log")
df_failures.to_csv(failures_log_path, index=False, encoding='utf-8')
print(f"  Trovati {len(df_failures)} fallimenti di fuzzy match per i farmaci.")
print(f"  Log salvato in: {failures_log_path}")

print("\nETL completato con successo!")
print("============================================================")
sys.stdout.close()
