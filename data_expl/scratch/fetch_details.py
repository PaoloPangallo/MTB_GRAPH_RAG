import requests
import json

token = "a5e4ab21-1ee2-4428-b2f2-363548057b0c"
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

def get_annotation(hugo, alteration, tumor):
    url = "https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange"
    params = {
        "hugoSymbol": hugo,
        "alteration": alteration,
        "tumorType": tumor
    }
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json()
    else:
        return {"error": r.status_code, "message": r.text}

if __name__ == "__main__":
    results = {}
    
    # 1. ALK G1202R in NSCLC
    results["ALK_G1202R_NSCLC"] = get_annotation("ALK", "G1202R", "NSCLC")
    
    # 2. ALK G1202R in Non-Small Cell Lung Cancer (full name)
    results["ALK_G1202R_Non_Small_Cell_Lung_Cancer"] = get_annotation("ALK", "G1202R", "Non-Small Cell Lung Cancer")
    
    # 3. MSI-High under MSH2 (often used for MSI-H/MMR-deficient tumors)
    results["MSH2_MSI_H_NSCLC"] = get_annotation("MSH2", "MSI-H", "Non-Small Cell Lung Cancer")
    
    # 4. MSI-H under MLH1
    results["MLH1_MSI_H_NSCLC"] = get_annotation("MLH1", "MSI-H", "Non-Small Cell Lung Cancer")
    
    with open("scratch/oncokb_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
        
    print("Fetched all data and saved to scratch/oncokb_results.json!")
