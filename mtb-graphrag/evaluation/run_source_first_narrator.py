"""Re-narrate three archived BRAF publication cases with cached bibliography."""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.narrator import call_dossier_narrator
from backend.research_pipeline.narrative.verifier import verify_narrative


def inputs():
    archive = REPO.parent / 'experiments_real/remaining_fixes_20261015/live4/E2E20-16/dossier.json'
    archived = json.loads(archive.read_text(encoding='utf-8'))['dossier']
    for pmid in ('28891408', '22663011', '24508103'):
        identity = 'pmid:' + pmid
        original = next(entry for entry in archived['paper_evidence']
                        if any(f['source'].get('public_source_identity') == identity
                               for f in entry.get('documentary_findings', [])))
        dossier = deepcopy(archived)
        entry = deepcopy(original)
        metadata_path = REPO / 'data_cache/document_grounding/pubmed/metadata' / (pmid + '.json')
        cached = json.loads(metadata_path.read_text(encoding='utf-8'))
        metadata = cached['result'][pmid]
        assert str(metadata['uid']) == pmid
        source = next(f['source'] for f in entry['documentary_findings']
                      if f['source'].get('public_source_identity') == identity)
        entry['source_bibliography'] = [{
            'document_id': source['document_id'], 'public_source_identity': identity,
            'title': metadata['title'], 'journal': metadata.get('fulljournalname'),
        }]
        dossier['paper_evidence'] = [entry]
        dossier['clinical_trials'] = []
        dossier['kg_only_relations'] = []
        dossier['documentary_summary'] = {}
        # Existing operational notices are retained in the archive, not turned
        # into mandatory prose about every selected publication.
        yield {'name': 'BRAF_' + pmid, 'canonical_dossier': dossier,
               'provenance': [{'file': p.relative_to(REPO.parent).as_posix(),
                               'sha256': sha256(p.read_bytes()).hexdigest()}
                              for p in (archive, metadata_path)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for index, item in enumerate(inputs(), 1):
        print(str(index) + '/3 ' + item['name'], flush=True)
        dossier = item['canonical_dossier']
        source = build_narrator_input(dossier)
        item['narrator_input'] = source
        if args.live:
            call = call_dossier_narrator(item['name'], source)
            item['call'] = call
            item['verification'] = verify_narrative(dossier, source, call.get('narrative'))
            print(call['transport_result'], item['verification']['status'],
                  item['verification']['reason_codes'], flush=True)
        results.append(item)
        (args.out / 'results.json').write_text(json.dumps({
            'mode': 'LIVE_MODEL' if args.live else 'PREPARED_WITHOUT_MODEL_CALLS', 'cases': results},
            ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
