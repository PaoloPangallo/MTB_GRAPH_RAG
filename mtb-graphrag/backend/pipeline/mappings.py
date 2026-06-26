"""
Dizionario di mapping KB locale (CIViC) ↔ OncoKB API.
I nomi dei biomarker differiscono tra le due sorgenti:
  KB:      "TMB High"  /  "MSI High"
  OncoKB:  "TMB-H"     /  "MSI-H"
"""

KB_TO_ONCOKB: dict[str, str] = {
    "TMB High":  "TMB-H",
    "MSI High":  "MSI-H",
}

ONCOKB_TO_KB: dict[str, str] = {v: k for k, v in KB_TO_ONCOKB.items()}
