from typing import List, Union
from .drug_aliases import parse_drug_combinations
from .contraindications import get_contraindications

def calculate_therapeutic_match(recommendations: Union[str, List[str]], expected_drug: str) -> float:
    """
    Calcola il match terapeutico tra le raccomandazioni del modello e il farmaco atteso.
    Restituisce:
      1.0 = Match completo (tutti i farmaci attesi sono presenti)
      0.5 = Match parziale (almeno un farmaco atteso è presente, tipicamente in una combinazione)
      0.0 = Match assente
    """
    if not expected_drug:
        return 0.0
        
    expected_list = parse_drug_combinations(expected_drug)
    if not expected_list:
        return 0.0

    # Estrai i farmaci raccomandati o usa il testo completo
    is_text = False
    if isinstance(recommendations, str):
        if len(recommendations) > 200: # È un report completo
            rec_text = recommendations.lower()
            is_text = True
        else:
            rec_list = parse_drug_combinations(recommendations)
    else:
        rec_list = []
        for r in recommendations:
            rec_list.extend(parse_drug_combinations(r))
            
    match_count = 0
    for ed in expected_list:
        if is_text:
            if ed in rec_text:
                match_count += 1
        else:
            if ed in rec_list:
                match_count += 1
    
    if match_count == len(expected_list):
        return 1.0
    elif match_count > 0:
        return 0.5
    else:
        return 0.0


def calculate_evidence_grounding(citations: List[str], valid_pmids: List[str]) -> bool:
    """
    Verifica se ALMENO UN PMID citato dal modello a supporto del farmaco
    è presente nell'elenco dei PMID considerati validi per quel profilo.
    """
    if not citations or not valid_pmids:
        return False
        
    cit_set = set([str(c).strip() for c in citations])
    valid_set = set([str(v).strip() for v in valid_pmids])
    
    return len(cit_set.intersection(valid_set)) > 0


def calculate_safety(recommendations: Union[str, List[str]], case_id: str) -> bool:
    """
    Verifica se la raccomandazione del modello vìola una controindicazione nota.
    Restituisce:
      True = Sicuro (nessuna controindicazione violata)
      False = Non sicuro (almeno un farmaco controindicato è stato raccomandato)
    """
    contraindications = get_contraindications(case_id)
    if not contraindications:
        return True
        
    is_text = False
    if isinstance(recommendations, str):
        if len(recommendations) > 200:
            rec_text = recommendations.lower()
            is_text = True
        else:
            rec_list = parse_drug_combinations(recommendations)
    else:
        rec_list = []
        for r in recommendations:
            rec_list.extend(parse_drug_combinations(r))
            
    for contra in contraindications:
        if is_text:
            if contra in rec_text:
                return False
        else:
            if contra in rec_list:
                return False
                
    return True
