import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from backend.pipeline.helpers import run_cypher

def verify_progression():
    print("==================================================")
    print(" VERIFICA 1: La catena di base esiste? (T790M -> OSIMERTINIB -> C797S)")
    print("==================================================\n")
    
    q1a = """
    MATCH (v1:Variant)-[:IN_MOLECULAR_PROFILE]->(mp1:MolecularProfile)-[:HAS_EVIDENCE]->(e1:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE toLower(v1.variant_name) = 't790m' 
      AND toLower(d.drug_name) = 'osimertinib' 
      AND e1.significance = 'Sensitivity/Response'
    RETURN DISTINCT v1.variant_name AS variant, d.drug_name AS drug, e1.significance AS significance, e1.evidence_level AS level
    ORDER BY level LIMIT 5
    """
    res1a = run_cypher(q1a)
    print("-> T790M e farmaco di sensibilità (Osimertinib):")
    if res1a:
        for r in res1a: print(r)
    else:
        print("Non trovato.")
        
    q1b = """
    MATCH (v2:Variant)-[:IN_MOLECULAR_PROFILE]->(mp2:MolecularProfile)-[:HAS_EVIDENCE]->(e2:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE toLower(v2.variant_name) CONTAINS 'c797s' 
      AND toLower(d.drug_name) = 'osimertinib' 
      AND e2.significance = 'Resistance'
    RETURN DISTINCT v2.variant_name AS variant, d.drug_name AS drug, e2.significance AS significance, e2.evidence_level AS level
    ORDER BY level LIMIT 5
    """
    res1b = run_cypher(q1b)
    print("\n-> C797S e sua relazione con Osimertinib (Resistenza):")
    if res1b:
        for r in res1b: print(r)
    else:
        print("Non trovato.")


    print("\n==================================================")
    print(" VERIFICA 2: Il passo successivo esiste? (C797S -> Sensibilità)")
    print("==================================================\n")
    
    q2 = """
    MATCH (v:Variant)-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE toLower(v.variant_name) CONTAINS 'c797s' 
      AND e.significance = 'Sensitivity/Response'
    RETURN DISTINCT v.variant_name AS variant, d.drug_name AS drug, e.evidence_level AS level
    ORDER BY level
    """
    res2 = run_cypher(q2)
    if res2:
        for r in res2: print(r)
    else:
        print("Non trovato.")
        
        
    print("\n==================================================")
    print(" VERIFICA 3: Quanto è generale? (T790M, C797S, G1202R, T315I)")
    print("==================================================\n")
    
    variants = ["T790M", "C797S", "G1202R", "T315I"]
    print(f"{'VARIANTE':<15} | {'RESISTENTE A':<45} | {'FARMACI ALTERNATIVI (SENSIBILITA)':<45}")
    print("-" * 110)
    
    for v in variants:
        q_res = """
        MATCH (var:Variant)-[:IN_MOLECULAR_PROFILE]->(mp)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
        WHERE toLower(var.variant_name) CONTAINS toLower($var) AND e.significance = 'Resistance'
        RETURN DISTINCT d.drug_name AS drug
        """
        res_res = run_cypher(q_res, {"var": v})
        res_drugs = [r['drug'] for r in res_res] if res_res else []
        
        q_sens = """
        MATCH (var:Variant)-[:IN_MOLECULAR_PROFILE]->(mp)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
        WHERE toLower(var.variant_name) CONTAINS toLower($var) AND e.significance = 'Sensitivity/Response'
        RETURN DISTINCT d.drug_name AS drug
        """
        res_sens = run_cypher(q_sens, {"var": v})
        sens_drugs = [r['drug'] for r in res_sens] if res_sens else []
        
        res_str = ", ".join(res_drugs)[:42] + ("..." if len(", ".join(res_drugs)) > 42 else "")
        sens_str = ", ".join(sens_drugs)[:42] + ("..." if len(", ".join(sens_drugs)) > 42 else "")
        if not res_drugs: res_str = "Non trovato"
        if not sens_drugs: sens_str = "Non trovato"
        
        print(f"{v:<15} | {res_str:<45} | {sens_str:<45}")

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    verify_progression()
