"""Source details stay visible independently of the model's explanatory prose."""
from __future__ import annotations

from copy import deepcopy

from ..documents.bibliography import source_url
from .evidence_sources import paper_sources


def build_source_cards(entry: dict) -> list[dict]:
    if 'documentary_findings' in entry:
        sources = []
        for finding in entry.get('documentary_findings') or []:
            source = finding.get('source') or {}
            authenticated = (finding.get('disposition') == 'RETAINED_RECORD'
                             and (finding.get('checks', {}).get('quotation') or {}).get('status') == 'AUTHENTICATED')
            quote = finding.get('quotation') if authenticated else None
            sources.append({**deepcopy(source), 'quote_available': bool(quote),
                            'validated_quote': quote, 'disposition': finding.get('disposition')})
    else:
        sources = deepcopy(paper_sources(entry))
    bibliography = entry.get('source_bibliography') or []
    represented = {str(source.get(key)).casefold() for source in sources
                   for key in ('document_id', 'public_source_identity', 'paper_id') if source.get(key)}
    for item in bibliography:
        identities = {str(item.get(key)).casefold() for key in ('document_id', 'public_source_identity') if item.get(key)}
        if identities and not identities & represented:
            sources.append({'document_id': item.get('document_id'),
                            'public_source_identity': item.get('public_source_identity'),
                            'quote_available': False, 'validated_quote': None,
                            'disposition': 'METADATA_ONLY'})
            represented.update(identities)
    result = []
    for source in sources:
        identities = {str(source.get(key)).casefold() for key in ('document_id', 'public_source_identity', 'paper_id')
                      if source.get(key)}
        matches = [item for item in bibliography if identities & {
            str(item.get(key)).casefold() for key in ('document_id', 'public_source_identity') if item.get(key)}]
        public_ids = {item.get('public_source_identity') for item in matches if item.get('public_source_identity')}
        public = source.get('public_source_identity') or (next(iter(public_ids)) if len(public_ids) == 1 else None)
        public = public or source.get('document_id') or source.get('paper_id') or ''
        titles = {item.get('title') for item in matches if isinstance(item.get('title'), str) and item['title'].strip()}
        journals = {item.get('journal') for item in matches if isinstance(item.get('journal'), str) and item['journal'].strip()}
        result.append({**source, 'paper_id': source.get('paper_id') or source.get('document_id') or public,
                       'public_source_identity': public,
                       'title': next(iter(titles)) if len(titles) == 1 else None,
                       'journal': next(iter(journals)) if len(journals) == 1 else None,
                       'url': source_url(public)})
    return result
