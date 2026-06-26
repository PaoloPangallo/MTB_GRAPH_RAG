from backend.pipeline.helpers import run_cypher

def count():
    n_ev = run_cypher("MATCH (e:Evidence) RETURN count(e) AS c")[0]["c"]
    n_pub = run_cypher("MATCH (p:Publication) RETURN count(p) AS c")[0]["c"]
    n_drug = run_cypher("MATCH (d:Drug) RETURN count(d) AS c")[0]["c"]
    n_trial = run_cypher("MATCH (ct:ClinicalTrial) RETURN count(ct) AS c")[0]["c"]
    n_cdx = run_cypher("MATCH (cd:CompanionDiagnostic) RETURN count(cd) AS c")[0]["c"]
    n_mp = run_cypher("MATCH (mp:MolecularProfile) RETURN count(mp) AS c")[0]["c"]
    
    print(f"Total Evidence: {n_ev}")
    print(f"Total Publications: {n_pub}")
    print(f"Total Drugs: {n_drug}")
    print(f"Total Trials: {n_trial}")
    print(f"Total Companion Diagnostics: {n_cdx}")
    print(f"Total Molecular Profiles: {n_mp}")

if __name__ == "__main__":
    count()
