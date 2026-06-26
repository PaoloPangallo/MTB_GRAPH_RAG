import requests

def test_pubmed():
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=EGFR+L858R+Lung&retmode=json&retmax=1"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        print(f"PubMed connection OK! Response: {r.json().keys()}")
        return True
    except Exception as e:
        print(f"PubMed connection failed: {e}")
        return False

def test_oncokb():
    url = "https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange"
    # use token from env or dummy query
    try:
        r = requests.get(url, params={"hugoSymbol": "EGFR", "alteration": "L858R", "tumorType": "Lung Adenocarcinoma"}, timeout=10)
        # Note: might return 401 if token is missing, but if it reaches the server it's OK
        print(f"OncoKB connection status: {r.status_code}")
        return True
    except Exception as e:
        print(f"OncoKB connection failed: {e}")
        return False

if __name__ == "__main__":
    test_pubmed()
    test_oncokb()
