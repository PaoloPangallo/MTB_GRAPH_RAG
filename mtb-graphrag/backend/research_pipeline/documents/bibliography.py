"""Presentation metadata bound to explicit document-resolution identities."""
from __future__ import annotations

import re


def source_url(identifier: str) -> str | None:
    if re.fullmatch(r'pmid:\d+', identifier, flags=re.I):
        return 'https://pubmed.ncbi.nlm.nih.gov/' + identifier.split(':')[1] + '/'
    if re.fullmatch(r'(?:pmcid:)?PMC\d+', identifier, flags=re.I):
        return 'https://pmc.ncbi.nlm.nih.gov/articles/' + identifier.split(':')[-1].upper() + '/'
    return None


def resolved_bibliography(documents, manifest: dict) -> list[dict]:
    """Copy existing metadata; identifiers come from explicit resolver lineage."""
    result = []
    for document in documents:
        if document is None:
            continue
        requested = document.lineage.get('requested_document_id') or document.document_id
        actual = manifest.get(document.document_id) or {}
        public = manifest.get(requested) or {}
        metadata = actual if actual.get('title') else public
        result.append({'document_id': document.document_id,
                       'public_source_identity': requested,
                       'title': metadata.get('title'), 'journal': metadata.get('journal')})
    return result
