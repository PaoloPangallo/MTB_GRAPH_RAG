import os
import re
import json
import pandas as pd
import numpy as np

# Directory paths
BASE_DIR = r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\DatasetTESI\Dataset TESI"
CSV_DIR = os.path.join(BASE_DIR, "Clean_Graph_Data")

# File paths
GENE_PATH = os.path.join(CSV_DIR, "node_gene.csv")
VARIANT_PATH = os.path.join(CSV_DIR, "node_variant.csv")
MP_PATH = os.path.join(CSV_DIR, "node_molecular_profile.csv")
EVIDENCE_PATH = os.path.join(CSV_DIR, "node_evidence.csv")
DRUG_PATH = os.path.join(CSV_DIR, "node_drug.csv")

EDGE_HAS_VARIANT_PATH = os.path.join(CSV_DIR, "edge_has_variant.csv")
EDGE_IN_MP_PATH = os.path.join(CSV_DIR, "edge_in_molecular_profile.csv")
EDGE_HAS_EVIDENCE_PATH = os.path.join(CSV_DIR, "edge_has_evidence.csv")
EDGE_TARGETS_DRUG_PATH = os.path.join(CSV_DIR, "edge_targets_drug.csv")

def normalize_name(name):
    if pd.isna(name):
        return ""
    val = str(name).upper().strip()
    val = re.sub(r'\b(HYDROCHLORIDE|SULFATE|TARTRATE|CITRATE|MALEATE|PHOSPHATE)\b', '', val)
    val = re.sub(r'[^A-Z0-9]', '', val)
    return val

def main():
    print("============================================================")
    print("ONCOKB KNOWLEDGE GRAPH ENRICHMENT PIPELINE (MSI + TMB + ALK)")
    print("============================================================")
    
    # 1. Load existing CSVs
    print("Caricamento dataset correnti...")
    df_genes = pd.read_csv(GENE_PATH)
    df_variants = pd.read_csv(VARIANT_PATH)
    df_mps = pd.read_csv(MP_PATH)
    df_evidence = pd.read_csv(EVIDENCE_PATH)
    df_drugs = pd.read_csv(DRUG_PATH)
    
    df_edge_has_variant = pd.read_csv(EDGE_HAS_VARIANT_PATH)
    df_edge_in_mp = pd.read_csv(EDGE_IN_MP_PATH)
    df_edge_has_evidence = pd.read_csv(EDGE_HAS_EVIDENCE_PATH)
    df_edge_targets_drug = pd.read_csv(EDGE_TARGETS_DRUG_PATH)
    
    # Load raw OncoKB results
    print("Caricamento dei file JSON di OncoKB...")
    with open("scratch/oncokb_results.json", "r", encoding="utf-8") as f:
        oncokb_results = json.load(f)
        
    with open("scratch/msi_results.json", "r", encoding="utf-8") as f:
        msi_results = json.load(f)
        
    with open("scratch/tmb_results_specific.json", "r", encoding="utf-8") as f:
        tmb_results = json.load(f)
        
    # Pre-build lookup maps
    drug_name_map = {}
    for _, row in df_drugs.iterrows():
        norm = normalize_name(row['drug_name'])
        if norm:
            drug_name_map[norm] = row['concept_id']
        norm_claim = normalize_name(row['drug_claim_name'])
        if norm_claim:
            drug_name_map[norm_claim] = row['concept_id']
            
    print(f"  Mappa dei farmaci correnti: {len(drug_name_map)} farmaci indicizzati.")
    
    # Help function to get or create drug in dataframe
    def get_or_create_drug(drug_name):
        norm = normalize_name(drug_name)
        if norm in drug_name_map:
            return drug_name_map[norm]
        
        # Create a new concept ID
        concept_id = f"fda:{norm}"
        print(f"  [NUOVO FARMACO] Creando nodo Drug per {drug_name} ({concept_id})")
        new_row = {
            'concept_id': concept_id,
            'drug_claim_name': drug_name,
            'nomenclature': 'FDA Precision Oncology',
            'drug_name': drug_name.upper(),
            'approved': True,
            'immunotherapy': False,
            'anti_neoplastic': True,
            'source_db_name': 'OncoKB_API',
            'source_db_version': 'v7.2',
            'fda_approval_year': None,
            'biomarker': None,
            'drug_class': 'OncoKB Added',
            'mechanism': 'Targeted Inhibitor'
        }
        nonlocal df_drugs
        df_drugs = pd.concat([df_drugs, pd.DataFrame([new_row])], ignore_index=True)
        drug_name_map[norm] = concept_id
        return concept_id

    # ------------------------------------------------------------
    # STEP 2: CREAZIONE NODO GENE FITTIZIO "Other Biomarkers"
    # ------------------------------------------------------------
    biomarker_entrez = -2
    if biomarker_entrez not in df_genes['entrez_id'].values:
        print("  [NUOVO GENE] Creando gene fittizio 'Other Biomarkers' (entrez_id: -2)")
        new_gene = {
            'entrez_id': biomarker_entrez,
            'hugo_symbol': 'Other Biomarkers',
            'gene_type': 'BIOMARKER',
            'is_oncokb_annotated': True,
            'grch38_isoform': '',
            'grch38_refseq': '',
            'aliases': 'MSI;TMB;HRD',
            'categories': 'BIOMARKER',
            'civic_description': 'Contenitore fittizio di OncoKB per alterazioni genomiche globali e firme tumorali'
        }
        df_genes = pd.concat([df_genes, pd.DataFrame([new_gene])], ignore_index=True)

    # ------------------------------------------------------------
    # STEP 3: CREAZIONE VARIANTI E PROFILI MOLECOLARI
    # ------------------------------------------------------------
    
    # 3.1 MSI-High variant and profile (ID: 200000)
    msi_variant_id = 200000
    msi_mp_id = 200000
    
    if msi_variant_id not in df_variants['variant_id'].values:
        print("  [NUOVA VARIANTE] Creando variante 'MSI-High' (variant_id: 200000)")
        new_var = {
            'variant_id': msi_variant_id,
            'variant_name': 'MSI-High',
            'feature_type': 'Biomarker',
            'hgvs_descriptions': 'MSI-H',
            'chromosome': 'N/A',
            'start': 0,
            'stop': 0,
            'reference_bases': 'N/A',
            'variant_bases': 'N/A',
            'variant_types': 'Genomic Indicator',
            'allele_registry_id': '',
            'civic_url': ''
        }
        df_variants = pd.concat([df_variants, pd.DataFrame([new_var])], ignore_index=True)
        
        # Link Gene -> Variant
        new_edge = {'source_entrez_id': biomarker_entrez, 'target_variant_id': msi_variant_id}
        df_edge_has_variant = pd.concat([df_edge_has_variant, pd.DataFrame([new_edge])], ignore_index=True)
        
    if msi_mp_id not in df_mps['molecular_profile_id'].values:
        print("  [NUOVO PROFILO] Creando profilo molecolare 'MSI-High' (molecular_profile_id: 200000)")
        new_mp = {
            'molecular_profile_id': msi_mp_id,
            'name': 'MSI-High',
            'summary': 'Stato fenotipico globale di instabilità dei microsatelliti',
            'evidence_score': 10.0,
            'aliases': 'MSI-H;Microsatellite Instability-High'
        }
        df_mps = pd.concat([df_mps, pd.DataFrame([new_mp])], ignore_index=True)
        
        # Link Variant -> MP
        new_edge = {'source_variant_id': msi_variant_id, 'target_molecular_profile_id': msi_mp_id}
        df_edge_in_mp = pd.concat([df_edge_in_mp, pd.DataFrame([new_edge])], ignore_index=True)

    # 3.2 TMB-High variant and profile (ID: 200002)
    tmb_variant_id = 200002
    tmb_mp_id = 200002
    
    if tmb_variant_id not in df_variants['variant_id'].values:
        print("  [NUOVA VARIANTE] Creando variante 'TMB-High' (variant_id: 200002)")
        new_var = {
            'variant_id': tmb_variant_id,
            'variant_name': 'TMB-High',
            'feature_type': 'Biomarker',
            'hgvs_descriptions': 'TMB-H',
            'chromosome': 'N/A',
            'start': 0,
            'stop': 0,
            'reference_bases': 'N/A',
            'variant_bases': 'N/A',
            'variant_types': 'Genomic Indicator',
            'allele_registry_id': '',
            'civic_url': ''
        }
        df_variants = pd.concat([df_variants, pd.DataFrame([new_var])], ignore_index=True)
        
        # Link Gene -> Variant
        new_edge = {'source_entrez_id': biomarker_entrez, 'target_variant_id': tmb_variant_id}
        df_edge_has_variant = pd.concat([df_edge_has_variant, pd.DataFrame([new_edge])], ignore_index=True)
        
    if tmb_mp_id not in df_mps['molecular_profile_id'].values:
        print("  [NUOVO PROFILO] Creando profilo molecolare 'TMB-High' (molecular_profile_id: 200002)")
        new_mp = {
            'molecular_profile_id': tmb_mp_id,
            'name': 'TMB-High',
            'summary': 'Tumor Mutational Burden-High (>=10 mut/Mb)',
            'evidence_score': 10.0,
            'aliases': 'TMB-H;TMB-High;Tumor Mutational Burden-High'
        }
        df_mps = pd.concat([df_mps, pd.DataFrame([new_mp])], ignore_index=True)
        
        # Link Variant -> MP
        new_edge = {'source_variant_id': tmb_variant_id, 'target_molecular_profile_id': tmb_mp_id}
        df_edge_in_mp = pd.concat([df_edge_in_mp, pd.DataFrame([new_edge])], ignore_index=True)

    # 3.3 ALK G1202R variant and profile (ID: 200001)
    alk_gene_id = 238
    alk_variant_id = None
    
    # Check if ALK G1202R already exists
    matched_vars = df_variants[df_variants['variant_name'].str.contains('G1202R', na=False, case=False)]
    if not matched_vars.empty:
        alk_variant_id = int(matched_vars.iloc[0]['variant_id'])
        print(f"  [VARIANTE ESISTENTE] Trovato ALK G1202R in Variant con ID {alk_variant_id}")
    else:
        alk_variant_id = 200001
        print(f"  [NUOVA VARIANTE] Creando variante 'ALK G1202R' (variant_id: 200001)")
        new_var = {
            'variant_id': alk_variant_id,
            'variant_name': 'ALK G1202R',
            'feature_type': 'Mutation',
            'hgvs_descriptions': 'ALK G1202R',
            'chromosome': '2',
            'start': 29443625,
            'stop': 29443625,
            'reference_bases': 'G',
            'variant_bases': 'A',
            'variant_types': 'Missense Mutation',
            'allele_registry_id': '',
            'civic_url': ''
        }
        df_variants = pd.concat([df_variants, pd.DataFrame([new_var])], ignore_index=True)
        
        # Link Gene -> Variant
        new_edge = {'source_entrez_id': alk_gene_id, 'target_variant_id': alk_variant_id}
        df_edge_has_variant = pd.concat([df_edge_has_variant, pd.DataFrame([new_edge])], ignore_index=True)

    # Resolve molecular profile for ALK G1202R
    alk_mp_id = None
    matched_mps = df_mps[df_mps['name'].str.contains('ALK G1202R', na=False, case=False)]
    if not matched_mps.empty:
        alk_mp_id = int(matched_mps.iloc[0]['molecular_profile_id'])
        print(f"  [PROFILO ESISTENTE] Trovato MolecularProfile per ALK G1202R con ID {alk_mp_id}")
    else:
        alk_mp_id = 200001
        print(f"  [NUOVO PROFILO] Creando profilo molecolare 'ALK G1202R' (molecular_profile_id: 200001)")
        new_mp = {
            'molecular_profile_id': alk_mp_id,
            'name': 'ALK G1202R',
            'summary': 'Acquired resistance mutation in ALK-rearranged solid tumors',
            'evidence_score': 8.0,
            'aliases': 'ALK G1202R;EML4-ALK G1202R'
        }
        df_mps = pd.concat([df_mps, pd.DataFrame([new_mp])], ignore_index=True)
        
        # Link Variant -> MP
        new_edge = {'source_variant_id': alk_variant_id, 'target_molecular_profile_id': alk_mp_id}
        df_edge_in_mp = pd.concat([df_edge_in_mp, pd.DataFrame([new_edge])], ignore_index=True)

    # ------------------------------------------------------------
    # STEP 4: PARSING EVIDENCE & CREAZIONE NODI EVIDENCE ONCOKB
    # ------------------------------------------------------------
    
    # We will reset OncoKB-specific evidence in the file to avoid duplicates,
    # or just start unique IDs at 100000. Let's filter out previous OncoKB nodes
    # so we do a clean recreation of the OncoKB data!
    print("Ripristino ed eliminazione di eventuali nodi OncoKB precedenti per evitare duplicati...")
    df_evidence = df_evidence[df_evidence['source_type'] != 'OncoKB'].copy()
    df_edge_has_evidence = df_edge_has_evidence[df_edge_has_evidence['target_evidence_id'] < 100000].copy()
    df_edge_targets_drug = df_edge_targets_drug[df_edge_targets_drug['source_evidence_id'] < 100000].copy()
    
    current_evidence_id = 100000
    
    new_evidences = []
    new_edge_has_evidences = []
    new_edge_targets_drugs = []
    
    # 4.1 Ingestion Evidenze ALK G1202R (da oncokb_results.json)
    alk_data = oncokb_results.get("ALK_G1202R_NSCLC", {})
    for rx in alk_data.get("treatments", []):
        level = rx.get("level")
        drugs_list = rx.get("drugs", [])
        pmids = rx.get("pmids", [])
        desc = rx.get("description", "")
        
        is_resistance = "LEVEL_R" in str(level)
        sig = "Resistance" if is_resistance else "Sensitivity/Response"
        ev_type = "Predictive"
        
        ev_id = current_evidence_id
        current_evidence_id += 1
        
        print(f"  [NUOVA EVIDENZA ALK] Creando Evidence {ev_id} ({level}) per ALK G1202R - {', '.join([d.get('drugName') for d in drugs_list])}")
        
        new_evidences.append({
            'evidence_id': ev_id,
            'evidence_type': ev_type,
            'evidence_level': level,
            'evidence_direction': 'Supports',
            'significance': sig,
            'evidence_statement': desc,
            'citation_id': ";".join(pmids) if pmids else "30892989",
            'source_type': 'OncoKB',
            'rating': 5 if not is_resistance else 4,
            'variant_origin': 'Somatic',
            'disease': 'Non-Small Cell Lung Cancer',
            'doid': '3908'
        })
        
        new_edge_has_evidences.append({
            'source_molecular_profile_id': alk_mp_id,
            'target_evidence_id': ev_id
        })
        
        for drug_info in drugs_list:
            drug_name = drug_info.get("drugName")
            drug_cid = get_or_create_drug(drug_name)
            
            new_edge_targets_drugs.append({
                'source_evidence_id': ev_id,
                'target_drug_concept_id': drug_cid,
                'evidence_level': level,
                'significance': sig,
                'evidence_direction': 'Supports'
            })

    # 4.2 Ingestion Evidenze MSI-High Colorectal (da msi_results.json)
    msi_colorectal_data = msi_results.get("MSI_H_Colorectal", {})
    for rx in msi_colorectal_data.get("treatments", []):
        level = rx.get("level")
        drugs_list = rx.get("drugs", [])
        pmids = rx.get("pmids", [])
        desc = rx.get("description", "")
        
        ev_id = current_evidence_id
        current_evidence_id += 1
        
        print(f"  [NUOVA EVIDENZA MSI CRC] Creando Evidence {ev_id} ({level}) per MSI-High Colorectal - {', '.join([d.get('drugName') for d in drugs_list])}")
        
        new_evidences.append({
            'evidence_id': ev_id,
            'evidence_type': 'Predictive',
            'evidence_level': level,
            'evidence_direction': 'Supports',
            'significance': 'Sensitivity/Response',
            'evidence_statement': desc,
            'citation_id': ";".join(pmids) if pmids else "29355075",
            'source_type': 'OncoKB',
            'rating': 5,
            'variant_origin': 'Somatic',
            'disease': 'Colorectal Cancer',
            'doid': '9256'
        })
        
        new_edge_has_evidences.append({
            'source_molecular_profile_id': msi_mp_id,
            'target_evidence_id': ev_id
        })
        
        for drug_info in drugs_list:
            drug_name = drug_info.get("drugName")
            drug_cid = get_or_create_drug(drug_name)
            
            new_edge_targets_drugs.append({
                'source_evidence_id': ev_id,
                'target_drug_concept_id': drug_cid,
                'evidence_level': level,
                'significance': 'Sensitivity/Response',
                'evidence_direction': 'Supports'
            })

    # 4.3 Ingestion Evidenze MSI-High NSCLC / Solid tumors (da msi_results.json)
    msi_nsclc_data = msi_results.get("MSI_H_NSCLC", {})
    for rx in msi_nsclc_data.get("treatments", []):
        level = rx.get("level")
        drugs_list = rx.get("drugs", [])
        pmids = rx.get("pmids", [])
        desc = rx.get("description", "")
        cancer_type_name = rx.get("levelAssociatedCancerType", {}).get("mainType", {}).get("name", "All Solid Tumors")
        
        ev_id = current_evidence_id
        current_evidence_id += 1
        
        print(f"  [NUOVA EVIDENZA MSI SOLID] Creando Evidence {ev_id} ({level}) per MSI-High {cancer_type_name} - {', '.join([d.get('drugName') for d in drugs_list])}")
        
        new_evidences.append({
            'evidence_id': ev_id,
            'evidence_type': 'Predictive',
            'evidence_level': level,
            'evidence_direction': 'Supports',
            'significance': 'Sensitivity/Response',
            'evidence_statement': desc,
            'citation_id': ";".join(pmids) if pmids else "30589920",
            'source_type': 'OncoKB',
            'rating': 5,
            'variant_origin': 'Somatic',
            'disease': cancer_type_name if cancer_type_name else 'Cancer',
            'doid': '162'
        })
        
        new_edge_has_evidences.append({
            'source_molecular_profile_id': msi_mp_id,
            'target_evidence_id': ev_id
        })
        
        for drug_info in drugs_list:
            drug_name = drug_info.get("drugName")
            drug_cid = get_or_create_drug(drug_name)
            
            new_edge_targets_drugs.append({
                'source_evidence_id': ev_id,
                'target_drug_concept_id': drug_cid,
                'evidence_level': level,
                'significance': 'Sensitivity/Response',
                'evidence_direction': 'Supports'
            })

    # 4.4 Ingestion Evidenze TMB-High (da tmb_results_specific.json)
    tmb_nsclc_data = tmb_results.get("TMB_H_NSCLC", {})
    for rx in tmb_nsclc_data.get("treatments", []):
        level = rx.get("level")
        drugs_list = rx.get("drugs", [])
        pmids = rx.get("pmids", [])
        desc = rx.get("description", "")
        cancer_type_name = rx.get("levelAssociatedCancerType", {}).get("mainType", {}).get("name", "All Solid Tumors")
        
        ev_id = current_evidence_id
        current_evidence_id += 1
        
        print(f"  [NUOVA EVIDENZA TMB SOLID] Creando Evidence {ev_id} ({level}) per TMB-High {cancer_type_name} - {', '.join([d.get('drugName') for d in drugs_list])}")
        
        new_evidences.append({
            'evidence_id': ev_id,
            'evidence_type': 'Predictive',
            'evidence_level': level,
            'evidence_direction': 'Supports',
            'significance': 'Sensitivity/Response',
            'evidence_statement': desc,
            'citation_id': ";".join(pmids) if pmids else "32919526",
            'source_type': 'OncoKB',
            'rating': 5,
            'variant_origin': 'Somatic',
            'disease': cancer_type_name if cancer_type_name else 'Cancer',
            'doid': '162'
        })
        
        new_edge_has_evidences.append({
            'source_molecular_profile_id': tmb_mp_id,
            'target_evidence_id': ev_id
        })
        
        for drug_info in drugs_list:
            drug_name = drug_info.get("drugName")
            drug_cid = get_or_create_drug(drug_name)
            
            new_edge_targets_drugs.append({
                'source_evidence_id': ev_id,
                'target_drug_concept_id': drug_cid,
                'evidence_level': level,
                'significance': 'Sensitivity/Response',
                'evidence_direction': 'Supports'
            })

    # ------------------------------------------------------------
    # STEP 5: SALVATAGGIO DEI DATI INTEGRATI NEI FILE CSV
    # ------------------------------------------------------------
    print("\nSalvataggio e consolidamento dei CSV arricchiti...")
    
    # Concatenate nodes
    df_evidence_final = pd.concat([df_evidence, pd.DataFrame(new_evidences)], ignore_index=True)
    
    # Concatenate edges
    df_edge_has_evidence_final = pd.concat([df_edge_has_evidence, pd.DataFrame(new_edge_has_evidences)], ignore_index=True)
    df_edge_targets_drug_final = pd.concat([df_edge_targets_drug, pd.DataFrame(new_edge_targets_drugs)], ignore_index=True)
    
    # Write nodes back
    df_genes.to_csv(GENE_PATH, index=False, encoding='utf-8')
    df_variants.to_csv(VARIANT_PATH, index=False, encoding='utf-8')
    df_mps.to_csv(MP_PATH, index=False, encoding='utf-8')
    df_drugs.to_csv(DRUG_PATH, index=False, encoding='utf-8')
    df_evidence_final.to_csv(EVIDENCE_PATH, index=False, encoding='utf-8')
    
    # Write edges back
    df_edge_has_variant.to_csv(EDGE_HAS_VARIANT_PATH, index=False, encoding='utf-8')
    df_edge_in_mp.to_csv(EDGE_IN_MP_PATH, index=False, encoding='utf-8')
    df_edge_has_evidence_final.to_csv(EDGE_HAS_EVIDENCE_PATH, index=False, encoding='utf-8')
    df_edge_targets_drug_final.to_csv(EDGE_TARGETS_DRUG_PATH, index=False, encoding='utf-8')
    
    print("\n============================================================")
    print("ENRICHMENT COMPLETATO CON SUCCESSO!")
    print(f"  Nodi Gene:              {len(df_genes)}")
    print(f"  Nodi Variant:           {len(df_variants)}")
    print(f"  Nodi MolecularProfile:  {len(df_mps)}")
    print(f"  Nodi Drug:              {len(df_drugs)}")
    print(f"  Nodi Evidence:          {len(df_evidence_final)} (aggiunti +{len(new_evidences)})")
    print(f"  Archi HAS_EVIDENCE:     {len(df_edge_has_evidence_final)} (aggiunti +{len(new_edge_has_evidences)})")
    print(f"  Archi TARGETS_DRUG:     {len(df_edge_targets_drug_final)} (aggiunti +{len(new_edge_targets_drugs)})")
    print("============================================================")

if __name__ == "__main__":
    main()
