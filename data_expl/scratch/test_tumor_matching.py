import pandas as pd
import re

df_bench = pd.read_csv('benchmark_papers_summary_30.csv')

TUMOR_SYNONYMS = {
    "nsclc": [
        "nsclc", "lung", "non-small cell", "non-small cell lung", 
        "non small cell lung", "adenocarcinoma of lung", "lung adenocarcinoma"
    ],
    "melanoma": [
        "melanoma", "cutaneous melanoma", "skin melanoma"
    ],
    "breast cancer her2+": [
        "breast", "mammary", "her2-positive", "her2+", "her2 positive"
    ],
    "breast cancer hr+": [
        "breast", "mammary", "hormone receptor-positive", "hr+", "hr-positive", "estrogen receptor-positive"
    ],
    "ovarian cancer": [
        "ovarian", "ovary", "fallopian tube", "peritoneal"
    ],
    "cml": [
        "leukemia", "myelogenous", "myeloid", "cml", "chronic myeloid", "chronic myelogenous", "chronic granulocytic"
    ],
    "colorectal cancer": [
        "colorectal", "colon", "rectum", "colonic", "rectal"
    ],
    "gist": [
        "gist", "gastrointestinal stromal"
    ],
    "aml": [
        "leukemia", "acute myeloid", "acute myelogenous", "aml", "myeloblast"
    ],
    "solid tumor": [
        "solid tumor", "solid cancer", "advanced solid", "tumor agnost", "any solid", "cancer", "carcinoma"
    ],
    "gastric cancer": [
        "gastric", "stomach", "gastroesophageal", "esophageal"
    ],
    "prostate cancer": [
        "prostate", "prostatic"
    ],
    "cholangiocarcinoma": [
        "cholangiocarcinoma", "bile duct", "biliary"
    ],
    "thyroid cancer": [
        "thyroid", "papillary thyroid", "anaplastic thyroid", "follicular thyroid"
    ]
}

def is_tumor_compatible(bench_tumor, kb_tumor):
    if not bench_tumor or not kb_tumor:
        return False
    bt_clean = bench_tumor.strip().lower()
    kbt_clean = kb_tumor.strip().lower()
    
    # Se coincidono direttamente
    if bt_clean in kbt_clean or kbt_clean in bt_clean:
        return True
        
    # Verifica tramite la mappa dei sinonimi
    if bt_clean in TUMOR_SYNONYMS:
        syns = TUMOR_SYNONYMS[bt_clean]
        for s in syns:
            if s in kbt_clean or kbt_clean in s:
                return True
    
    # Anche il contrario: se kb_tumor in qualche modo contiene acronimi o parole chiave del bench_tumor
    for b_key, syns in TUMOR_SYNONYMS.items():
        if b_key in bt_clean:
            for s in syns:
                if s in kbt_clean:
                    return True
                    
    # Gestione specifica tumor-agnostic
    if bt_clean == "solid tumor" or kbt_clean == "solid tumor":
        return True
        
    return False

# Testiamo su alcuni esempi
examples = [
    ("NSCLC", "Lung Non-small Cell Carcinoma"),
    ("Melanoma", "Cutaneous Melanoma"),
    ("CML", "Chronic Myelogenous Leukemia"),
    ("Colorectal Cancer", "Colon Carcinoma"),
    ("Breast Cancer HER2+", "Breast Cancer"),
]

for bt, kbt in examples:
    print(f"'{bt}' vs '{kbt}' ➔ {is_tumor_compatible(bt, kbt)}")
