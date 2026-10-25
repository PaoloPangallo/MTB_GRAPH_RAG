"""Resolution of accepted mentions; original parser artifacts remain intact."""
from copy import deepcopy
from functools import lru_cache
import re

from .registry import Registry, IDENTITY_SCOPES
from .surface import surface
from .molecular import resolve_variant, molecular_observation
from .disease_translations import ALIASES, CONTEXT_PHRASES, CONTEXT_WORDS, KNOWN_CONTEXT_WORDS, VERSION as TRANSLATION_VERSION

VERSION = 'disease-context-resolution/2.2'


# Source-backed clinical name used in abstracts for the DOID:3969 concept.
# NCI defines “papillary thyroid cancer”; Disease Ontology identifies
# papillary thyroid carcinoma as the corresponding concept.
_APPROVED_DISEASE_ALIASES = {
    surface('non-small-cell lung cancer'): {
        'canonical': 'Non-Small Cell Lung Carcinoma',
        'source': 'https://pubmed.ncbi.nlm.nih.gov/27870574/',
    },
    surface('sqNSCLC'): {
        'canonical': 'Lung Squamous Cell Carcinoma',
        'source': 'https://pubmed.ncbi.nlm.nih.gov/27870574/',
    },
    **{surface(key): {**value, 'origin': 'CURATED_APPLICATION_TRANSLATION', 'version': TRANSLATION_VERSION}
       for key, value in ALIASES.items()},
    surface("papillary thyroid cancer"): {
        "canonical": "Papillary Thyroid Carcinoma",
        "source": "https://www.cancer.gov/publications/dictionaries/cancer-terms/def/papillary-thyroid-cancer",
    },
    surface("mCRC"): {
        "canonical": "Colorectal Cancer",
        "residual_context": "metastatic",
        "source": "GCA4 curated acronym expansion: metastatic colorectal cancer",
    },
}


def _context(raw: str) -> tuple[str, list[str]]:
    normalized = surface(raw)
    for phrase, translation in CONTEXT_PHRASES.items():
        normalized = re.sub(r'(?<![\w-])' + re.escape(phrase) + r'(?![\w-])', translation, normalized)
    words = re.findall(r'[\w-]+', normalized)
    translated = [CONTEXT_WORDS.get(word, word) for word in words]
    return ' '.join(translated), [word for word in translated if word not in KNOWN_CONTEXT_WORDS]


def _same_context(left: str, right: str) -> bool:
    """Only independent, explicitly supported descriptors may change order.

    Keep stages, qualified phrases, negations and unknown text opaque.
    Neither token inclusion nor removal of repeated qualifiers proves identity.
    """
    if left == right:
        return True
    independent = {'metastatic', 'recurrent', 'advanced', 'resected', 'unresectable'}
    left_words, right_words = left.split(), right.split()
    return bool(left_words and right_words) and all(
        word in independent for word in (*left_words, *right_words)
    ) and sorted(left_words) == sorted(right_words)


def resolution_record(resolution):
    sources = sorted(set(t.source for t in resolution.terms), key=lambda s: (s.asset, s.locator))
    return {"domain": resolution.domain, "raw_value": resolution.raw_value, "status": resolution.status,
            "method": resolution.method, "concept_ids": resolution.concept_ids, "reasons": resolution.reasons,
            "registry_version": resolution.registry_version,
            "source_refs": [s.__dict__ for s in sources[:8]], "source_ref_count": len(sources)}


@lru_cache(maxsize=32768)
def disease_context(value: str, registry: Registry) -> dict:
    direct = registry.resolve("DISEASE", value)
    result = {**resolution_record(direct), "residual_context": "", "raw_residual_context": "", "match_span": None,
              'normalization_version': VERSION}
    if direct.status != "UNMAPPED":
        return result
    text = surface(value)
    approved_alias = _APPROVED_DISEASE_ALIASES.get(text)
    if approved_alias:
        resolved = registry.resolve("DISEASE", approved_alias["canonical"])
        if resolved.status == "RESOLVED":
            return {
                **resolution_record(resolved), "raw_value": value,
                "method": "APPROVED_DISEASE_ALIAS",
                "residual_context": approved_alias.get("residual_context", ""),
                'raw_residual_context': '', 'normalization_version': VERSION,
                "match_span": {"start": 0, "end": len(text), "coordinate_system": "NORMALIZED_MENTION"},
                "approved_alias_source": approved_alias["source"],
                'alias_origin': approved_alias.get('origin', 'APPROVED_ALIAS'),
                'translation_version': approved_alias.get('version'),
            }
    # Longest source-backed phrase, preserving every unmatched qualifier.
    # This is mention segmentation, never an ontology hierarchy inference.
    if getattr(registry, '_disease_phrase_index_version', None) != VERSION:
        index = {}
        for term in registry.terms:
            if term.domain == "DISEASE" and term.alias_scope in IDENTITY_SCOPES:
                key = surface(term.label)
                index.setdefault(key.split()[0], set()).add(key)
        for alias in _APPROVED_DISEASE_ALIASES:
            index.setdefault(alias.split()[0], set()).add(alias)
        registry._disease_phrase_index = index
        registry._disease_phrase_index_version = VERSION
    matches = []
    for word in re.finditer(r"(?<![\w-])[\w-]+", text):
        for label in registry._disease_phrase_index.get(word[0], ()):
            end = word.start() + len(label)
            if text[word.start():end] == label and (end == len(text) or not re.match(r'[\w-]', text[end])):
                alias = _APPROVED_DISEASE_ALIASES.get(label)
                canonical = alias["canonical"] if alias else label
                resolved = registry.resolve('DISEASE', canonical)
                if resolved.status == 'RESOLVED':
                    matches.append((word.start(), end, resolved, alias))
    # Suppress a phrase strictly contained in a more specific observed phrase.
    maximal = [m for m in matches if not any(n[0] <= m[0] and n[1] >= m[1] and n[:2] != m[:2] for n in matches)]
    ids = sorted({cid for _, _, r, _alias in maximal for cid in r.concept_ids})
    if len(ids) == 1 and maximal:
        start, end, resolved, alias = sorted(maximal, key=lambda x: (-(x[1]-x[0]), x[0]))[0]
        raw_context = (text[:start] + ' ' + text[end:]).strip()
        context, unresolved = _context(raw_context)
        if alias and alias.get('residual_context'):
            context = ' '.join(filter(None, [context, alias['residual_context']]))
        result = {**resolution_record(resolved), "raw_value": value, "method": "MENTION_SEGMENTATION",
                  "match_span": {"start": start, "end": end, "coordinate_system": "NORMALIZED_MENTION"},
                  "residual_context": context, 'raw_residual_context': raw_context,
                  'normalization_version': VERSION, "reasons": ["CONTEXT_RETAINED"]}
        if unresolved:
            result.update(status='UNMAPPED', concept_ids=(), partial_concept_ids=ids,
                          reasons=['PARTIAL_DISEASE_MENTION'], unresolved_context_words=unresolved)
        if alias:
            result.update(approved_alias_source=alias['source'], alias_origin=alias.get('origin', 'APPROVED_ALIAS'),
                          translation_version=alias.get('version'))
        return result
    if ids:
        result.update(status="AMBIGUOUS", concept_ids=ids, reasons=["COMPETING_DISEASE_MENTIONS"])
    return result


def disease_matches(query: str, candidate: str, registry: Registry) -> bool:
    left, right = disease_context(query, registry), disease_context(candidate, registry)
    if left["status"] == right["status"] == "RESOLVED":
        return set(left["concept_ids"]) == set(right["concept_ids"]) and (
            not right["residual_context"] or _same_context(left["residual_context"], right["residual_context"]))
    return left["status"] != "AMBIGUOUS" and right["status"] != "AMBIGUOUS" and bool(surface(query)) and surface(query) == surface(candidate)


@lru_cache(maxsize=8192)
def _ancestor_path(child: str, parent: str, registry: Registry) -> tuple[dict, ...]:
    if not hasattr(registry, '_disease_parent_edges'):
        edges: dict[str, list[dict]] = {}
        for edge in registry.mappings:
            if edge.get('predicate') == 'IS_A' and edge.get('source') and str(edge.get('subject', '')).startswith('DOID:'):
                edges.setdefault(edge['subject'], []).append(edge)
        registry._disease_parent_edges = edges
    queue = [(child, ())]
    seen = {child}
    for node, path in queue:
        for edge in registry._disease_parent_edges.get(node, []):
            next_path = (*path, edge)
            if edge['object'] == parent:
                return next_path
            if edge['object'] not in seen:
                seen.add(edge['object'])
                queue.append((edge['object'], next_path))
    return ()


def disease_retrieval_match(query: str, candidate: str, registry: Registry) -> dict:
    """Source-backed broader documents may be retrieved; never establish identity."""
    if disease_matches(query, candidate, registry):
        return {'eligible': True, 'scope': 'IDENTITY_CONTEXT_COMPATIBLE', 'ontology_path': []}
    left, right = disease_context(query, registry), disease_context(candidate, registry)
    if left['status'] != 'RESOLVED' or right['status'] != 'RESOLVED' or (
        right['residual_context'] and not _same_context(right['residual_context'], left['residual_context'])
    ):
        return {'eligible': False, 'scope': 'UNRESOLVED_OR_INCOMPATIBLE', 'ontology_path': []}
    generic = {cid for label in ('disease', 'cancer', 'carcinoma', 'adenocarcinoma', 'neoplasm')
               for cid in registry.resolve('DISEASE', label).concept_ids}
    for child in left['concept_ids']:
        for parent in right['concept_ids']:
            path = () if parent in generic else _ancestor_path(child, parent, registry)
            if path:
                return {'eligible': True, 'scope': 'SOURCE_BROADER_THAN_QUERY_NOT_IDENTITY', 'ontology_path': list(path)}
    return {'eligible': False, 'scope': 'NO_SUPPORTED_SCOPE_RELATION', 'ontology_path': []}


def compare_disease_context(expected: str, observed: str, registry: Registry) -> dict:
    """Compare concept and residual scope separately, without hierarchy inference.

    Residual text is opaque except for reordered independent descriptors.
    Similarity, token inclusion or absence cannot establish clinical equivalence.
    """
    left = disease_context(expected, registry)
    right = disease_context(observed, registry)
    relation = "UNKNOWN"
    if left["status"] == right["status"] == "RESOLVED":
        if left["concept_ids"] != right["concept_ids"]:
            relation = "DIFFERENT"
        elif not _same_context(left["residual_context"], right["residual_context"]):
            relation = "SAME_CONCEPT_CONTEXT_UNRESOLVED"
        else:
            relation = "VERIFIED_ALIAS"
    elif any(
        complete['status'] == 'RESOLVED'
        and partial['status'] == 'UNMAPPED'
        and partial.get('approved_alias_source')
        and 'PARTIAL_DISEASE_MENTION' in partial.get('reasons', ())
        and set(complete['concept_ids']) == set(partial.get('partial_concept_ids', ()))
        for complete, partial in ((left, right), (right, left))
    ):
        # A curated core name licenses contextual review only. The full mention
        # stays UNMAPPED, and neither identity nor retrieval is established.
        relation = 'SAME_CONCEPT_CONTEXT_UNRESOLVED'
    elif left["status"] != "AMBIGUOUS" and right["status"] != "AMBIGUOUS":
        if surface(expected) and surface(expected) == surface(observed):
            relation = "LITERAL_IDENTITY"
    if relation == "DIFFERENT":
        classification = "MISMATCH"
    elif relation in {"VERIFIED_ALIAS", "LITERAL_IDENTITY"}:
        classification = "MATCH"
    elif relation == "SAME_CONCEPT_CONTEXT_UNRESOLVED":
        classification = "MATCH_CONTEXTUAL"
    else:
        classification = "UNKNOWN"
    return {"relation": relation, "classification": classification,
            "expected": left, "observed": right}


def resolve_case(case_context: dict, registry: Registry) -> dict:
    result = deepcopy(case_context)
    diseases = list(result.get("diseases") or [])
    if not diseases and result.get("disease"):
        diseases = [result["disease"]]
    resolutions = {"registry_version": registry.version, "diseases": [], "biomarkers": [], "negated_biomarkers": [], "interventions": []}
    for value in diseases:
        raw = (value.get("raw_value") or value.get("normalized_value") or "") if isinstance(value, dict) else str(value)
        resolutions["diseases"].append(disease_context(raw, registry))
    for item in result.get("biomarkers") or []:
        gene = registry.resolve("GENE", item.get("gene") or "")
        variant = resolve_variant(gene, item.get("alteration") or "", registry)
        resolutions["biomarkers"].append({"gene": resolution_record(gene), "variant": resolution_record(variant),
                                         "assertion_status": item.get("assertion_status", "UNKNOWN"),
                                         "observation": molecular_observation(item, registry).to_dict()})
    for item in result.get("negated_biomarkers") or []:
        gene = registry.resolve("GENE", item.get("gene") or "")
        variant = resolve_variant(gene, item.get("alteration") or "", registry)
        resolutions["negated_biomarkers"].append({"gene": resolution_record(gene), "variant": resolution_record(variant),
                                                  "assertion_status": "NEGATED",
                                                  "observation": molecular_observation({**item, "assertion_status": "NEGATED"}, registry).to_dict()})
    # Follow the verified plural target contract used by retrieval. The scalar
    # field remains a compatibility fallback, not a reason to lose later targets.
    interventions = list(result.get('target_interventions') or [])
    if not interventions and result.get('target_intervention'):
        interventions = [result['target_intervention']]
    seen_interventions: set[str] = set()
    for intervention in interventions:
        raw = intervention.get("raw_value") or intervention.get("normalized_value") if isinstance(intervention, dict) else intervention
        identity = str(raw or '').strip().casefold()
        if not identity or identity in seen_interventions:
            continue
        seen_interventions.add(identity)
        resolved = resolution_record(registry.resolve("INTERVENTION", raw or ""))
        # Resolve named participants without inventing a regimen concept or
        # inferring administration together from a conjunction in the request.
        if resolved["status"] == "UNMAPPED":
            parts = re.split(r"\s+(?:e|and|plus)\s+|\s+\+\s+", str(raw or ""), flags=re.I)
            if len(parts) > 1 and all(part.strip() for part in parts):
                components = [resolution_record(registry.resolve("INTERVENTION", part.strip())) for part in parts]
                if any(item["status"] == "RESOLVED" for item in components):
                    resolved.update({"mention_structure": "CONJOINED_MENTION", "components": components,
                                     "component_resolution_status": "RESOLVED_COMPONENTS" if all(
                                         item["status"] == "RESOLVED" for item in components) else "PARTIAL_COMPONENTS"})
        resolutions["interventions"].append(resolved)
    statuses = [x["status"] for x in resolutions["diseases"] + resolutions["interventions"]]
    statuses.extend(x[k]["status"] for x in resolutions["biomarkers"] + resolutions["negated_biomarkers"] for k in ("gene", "variant"))
    resolutions["status_counts"] = {s: statuses.count(s) for s in sorted(set(statuses))}
    result["entity_resolution"] = resolutions
    return result
