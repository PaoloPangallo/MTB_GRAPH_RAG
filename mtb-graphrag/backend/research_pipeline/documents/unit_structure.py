"""Derived retrieval hierarchy; original unit text and identity remain intact."""
VERSION = 'sourceunit-structure/1.0'


def build_unit_structure(units: list[dict]) -> dict[str, dict]:
    parents = {}
    sections = set()
    for unit in units:
        kind = unit.get('unit_type', '')
        key = (unit.get('document_id'), unit.get('section'), unit.get('subsection'), unit.get('paragraph_index'))
        if kind in {'FULLTEXT_PARAGRAPH', 'ABSTRACT', 'ABSTRACT_SECTION'}:
            parents.setdefault(key, []).append(unit)
        if kind == 'ABSTRACT_SECTION':
            sections.add(unit.get('document_id'))
    result = {}
    for unit in units:
        uid, kind = unit['source_unit_id'], unit.get('unit_type', '')
        key = (unit.get('document_id'), unit.get('section'), unit.get('subsection'), unit.get('paragraph_index'))
        parent = None
        if kind.endswith('SENTENCE'):
            choices = [p for p in parents.get(key, []) if unit.get('text', '') in p.get('text', '')]
            if choices:
                parent = min(choices, key=lambda p: (len(p.get('text', '')), p['source_unit_id']))['source_unit_id']
        indexable = bool(str(unit.get('text') or '').strip()) and kind not in {
            'TITLE', 'FULLTEXT_SECTION', 'CONDITION', 'INTERVENTION'} and parent is None
        if kind == 'ABSTRACT' and unit.get('document_id') in sections:
            indexable = False
        result[uid] = {'version': VERSION, 'parent_id': parent, 'context_ids': [], 'indexable': indexable}
    # Table references are context links, never text concatenation into a quote.
    tables = {}
    for u in units:
        if u.get('table_id'):
            tables.setdefault((u.get('document_id'), u['table_id']), []).append(u)
    for group in tables.values():
        for u in group:
            if u.get('unit_type') == 'TABLE_CELL':
                result[u['source_unit_id']]['context_ids'] = [
                    v['source_unit_id'] for v in group if v['source_unit_id'] != u['source_unit_id']
                    and (v.get('unit_type') == 'TABLE_CAPTION' or v.get('row') == 0 or v.get('row') == u.get('row'))]
    return result
