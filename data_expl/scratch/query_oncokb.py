import requests
import json

token = "a5e4ab21-1ee2-4428-b2f2-363548057b0c"
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

def query_oncokb(hugo_symbol, alteration, tumor_type):
    url = "https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange"
    params = {
        "hugoSymbol": hugo_symbol,
        "alteration": alteration,
        "tumorType": tumor_type
    }
    print(f"--- Querying OncoKB for Gene: {hugo_symbol}, Alteration: {alteration}, Tumor Type: {tumor_type} ---")
    try:
        response = requests.get(url, headers=headers, params=params)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            # Extract key fields
            summary = {
                "query": {"gene": hugo_symbol, "alteration": alteration, "tumorType": tumor_type},
                "oncokbLevel": data.get("highestSensitiveLevel"),
                "highestSensitiveLevel": data.get("highestSensitiveLevel"),
                "highestResistanceLevel": data.get("highestResistanceLevel"),
                "mutationEffect": data.get("mutationEffect", {}).get("effect"),
                "oncogenic": data.get("oncogenic"),
                "treatments": []
            }
            
            # Extract clinical treatments and evidence levels
            for rx in data.get("treatments", []):
                summary["treatments"].append({
                    "level": rx.get("level"),
                    "drugs": [d.get("drugName") for d in rx.get("drugs", [])],
                    "approvedIndications": rx.get("approvedIndications"),
                    "pmids": rx.get("pmids")
                })
            
            print(json.dumps(summary, indent=2))
            return data
        else:
            print("Error response text:")
            print(response.text)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Test 1: ALK G1202R in NSCLC
    query_oncokb("ALK", "G1202R", "NSCLC")
    
    # Test 2: ALK G1202R in Non-Small Cell Lung Cancer
    query_oncokb("ALK", "G1202R", "Non-Small Cell Lung Cancer")
    
    # Test 3: MSI-High
    # MSI-H in OncoKB might be annotated differently. Let's try hugoSymbol=MSI or MSI-H, or MMR
    # Let's test "MSI-H" as alteration with some MMR genes like MSH2, MSH6, MLH1, PMS2 or general MMR
    query_oncokb("MSH2", "MSI-H", "Colorectal Cancer")
