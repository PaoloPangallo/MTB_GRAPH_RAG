"""Detect explicit extraction contradictions; not a scientific truth classifier."""
import re

VERSION = "documentary-observation-checks/1.1"


def assess_observation(quote: str, observed: dict) -> dict:
    codes = []
    objective = re.match(r"\s*(?:(?:PURPOSE|OBJECTIVE|OBJECTIVES|AIM)\s*:?\s*)?(?:to\s+(?:assess|evaluate|investigate|determine|compare)|we\s+aim(?:ed)?\s+to)\b", quote, re.I)
    result = re.search(r"\b(?:results?\s+(?:showed|demonstrated|revealed)|we\s+(?:found|observed)|response\s+rate\s+(?:was|of)|resulted\s+in|(?:regression|response|reduction)\s+(?:occurred|was|were)|(?:improved|increased|decreased)\s+(?:to|by))\b", quote, re.I)
    effect = observed.get('effect_direction')
    # Hard rejection is limited to an objective-only clause, not mixed prose.
    mixed = bool(re.search(r'[;.]\s*\w|\bwe\s+(?:treated|measured|enrolled)\b', quote.rstrip('.'), re.I))
    if objective and not result and not mixed and effect not in (None, '', 'UNKNOWN', 'NOT_APPLICABLE'):
        codes.append('OBJECTIVE_NOT_OBSERVED_RESULT')
    if observed.get('intervention_composition') == 'COMBINATION':
        if re.search(r'\brespectively\b', quote, re.I) and re.search(r'\b(?:trials|studies|separately)\b', quote, re.I):
            if not re.search(r'\b(?:combination|combined|coadministered|plus)\b', quote, re.I):
                codes.append('SEPARATE_INTERVENTIONS_NOT_COMBINATION')
    if observed.get('molecular_composition') in {'COMBINATION', 'COEXPRESSION'} or observed.get('relation_scope') in {'COMBINATION', 'COEXPRESSION'}:
        variant = r'\b[A-Z]\d+[A-Z]\b'
        alternatives = re.search(variant + r'\s+(?:or|oppure|versus|vs\.?)\s+(?:[A-Z]+\s+)?' + variant, quote)
        population = re.search(r'\b(?:patients|cohorts?|population|pazienti|coorti)\b', quote, re.I)
        enumerated = re.search(r'\b(?:compris\w*|includ\w*)\s+both\s+' + variant + r'\s+and\s+' + variant, quote, re.I)
        if alternatives or (population and enumerated):
            codes.append('ALTERNATIVE_VARIANTS_NOT_COALTERATION')
    return {'version': VERSION, 'status': 'MISMATCH' if codes else 'PASS',
            'reason_codes': codes, 'basis': 'EXPLICIT_TEXT_CONSISTENCY_ONLY',
            'scientific_correctness': 'NOT_INDEPENDENTLY_EVALUATED'}
