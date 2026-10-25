"""Source-linked phenotype identity and literal population scope, not efficacy."""
from __future__ import annotations

import re
from typing import Any

from ..terminology.matching import registry
from ..terminology.molecular import parse_profile, resolve_phenotype


def source_phenotype(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Require independently agreeing source labels, IDs, graph and atomic AST.

    Query fields and Reader assertions are deliberately not inputs.
    """
    source = (candidate.get('source_properties') or {}).get('profile') or {}
    name = source.get('name')
    if not isinstance(name, str):
        return None
    reg = registry()
    phenotype = resolve_phenotype(name, reg)
    profile = reg.resolve('PROFILE', name)
    if phenotype.status != 'RESOLVED' or profile.status != 'RESOLVED':
        return None
    pid = profile.concept_ids[0]
    graph_pid = pid.replace('CIViCProfile:', 'MolecularProfile:')
    if str(source.get('molecular_profile_id') or '') != pid.split(':', 1)[1]:
        return None
    subject = candidate.get('subject') or {}
    subject_identity = reg.resolve('PROFILE', subject.get('label') or '')
    if (subject.get('id') != graph_pid or subject.get('type') != 'MolecularProfile'
            or subject_identity.concept_ids != (pid,) or subject_identity.status != 'RESOLVED'):
        return None
    graph_profiles = [x for x in candidate.get('graph_path') or []
                      if isinstance(x, str) and x.startswith('MolecularProfile:')]
    if graph_profiles != [graph_pid]:
        return None
    graph_variants = {x.replace('Variant:', 'CIViCVariant:') for x in candidate.get('graph_path') or []
                      if isinstance(x, str) and x.startswith('Variant:')}
    if graph_variants != set(phenotype.concept_ids):
        return None
    linked = candidate.get('entity_resolution') or {}
    parsed = parse_profile(name, reg)
    if (linked.get('profile_id') != pid or linked.get('registry_version') != reg.version
            or linked.get('profile') != parsed or parsed.get('status') != 'RESOLVED'
            or (parsed.get('ast') or {}).get('op') != 'PHENOTYPE'
            or set(parsed.get('component_ids') or []) != set(phenotype.concept_ids)):
        return None
    return {'name': 'MSI', 'value': 'HIGH', 'source_profile_id': pid,
            'source_variant_ids': list(phenotype.concept_ids), 'registry_version': reg.version}


def phenotype_correspondence(target: dict[str, Any], observed: dict[str, Any], quote: str) -> str:
    """A literal BIOMARKER may confirm identity without proving any effect."""
    relation = observed.get('observed_relation') or {}
    for subject in relation.get('subjects') or []:
        if not isinstance(subject, dict) or str(subject.get('type') or '').upper() != 'BIOMARKER':
            continue
        value = subject.get('surface_value') or subject.get('value')
        if not isinstance(value, str) or not value:
            continue
        # Normalize punctuation for literal grounding only, not identity.
        tokens = lambda text: re.findall(r'[a-z0-9]+', str(text).casefold())
        sought, actual = tokens(value), tokens(quote)
        literal = bool(sought) and any(actual[i:i + len(sought)] == sought
                                      for i in range(len(actual) - len(sought) + 1))
        resolved = resolve_phenotype(value, registry())
        if literal and resolved.status == 'RESOLVED' and list(resolved.concept_ids) == target['source_variant_ids']:
            return 'CONFIRMED'
    return 'NOT_CONFIRMED'


def phenotype_population_scope(quote: str) -> dict[str, Any]:
    """Record an explicit adjacent logical condition; slash is ambiguous.

    This grammar audit does not equate dMMR and MSI-high or infer subgroup data.
    """
    high = r'(?:MSI[- ]H|microsatellite[- ]instability[- ]high)'
    other = r'(?:dMMR|mismatch[- ]repair[- ]deficient)'
    match = re.search(rf'\b{high}\s+(or|and)\s+{other}\b', quote, re.I)
    if not match:
        match = re.search(rf'\b{other}\s+(or|and)\s+{high}\b', quote, re.I)
    operator = match[1].upper() if match else 'UNKNOWN'
    span = match[0] if match else None
    return {'population_relation': {'OR': 'BROADER_OR_ALTERNATIVE', 'AND': 'INTERSECTION'}.get(operator, 'UNKNOWN'),
            'logical_operator': operator, 'literal_span': span,
            'subgroup_effect_established': False}
