import requests
import json

token = "a5e4ab21-1ee2-4428-b2f2-363548057b0c"
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

def get_by_url(url, params):
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json()
    else:
        return {"error": r.status_code, "message": r.text}

if __name__ == "__main__":
    results = {}
    
    # 1. MSI-H directly in Colorectal Cancer (no hugoSymbol)
    results["MSI_H_Colorectal"] = get_by_url(
        "https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange",
        {"alteration": "MSI-H", "tumorType": "Colorectal Cancer"}
    )
    
    # 2. MSI-H directly in NSCLC (no hugoSymbol)
    results["MSI_H_NSCLC"] = get_by_url(
        "https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange",
        {"alteration": "MSI-H", "tumorType": "NSCLC"}
    )
    
    with open("scratch/msi_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
        
    print("Fetched MSI-H data and saved to scratch/msi_results.json!")
