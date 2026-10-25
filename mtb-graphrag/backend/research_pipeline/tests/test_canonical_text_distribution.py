"""Distribution regressions: newline representation must not change trusted text."""
from __future__ import annotations

from hashlib import sha256
import json
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from backend.research_pipeline.enrichment import document_verification as verifier
from backend.research_pipeline.text_integrity import (
    CANONICAL_TEXT_DIGEST_VERSION,
    canonical_text_bytes,
    canonical_text_sha256,
)

RESOURCE = Path(verifier.__file__).resolve().parents[1] / 'resources'


@pytest.mark.parametrize('text', ['a\nb\n', 'a\r\nb\r\n', 'a\rb\r'])
def test_only_line_endings_are_normalized(text):
    assert canonical_text_sha256(text) == sha256(b'a\nb\n').hexdigest()


def test_trailing_newlines_and_other_characters_are_preserved():
    assert canonical_text_sha256('a') != canonical_text_sha256('a\n')
    assert canonical_text_sha256('a\n') != canonical_text_sha256('a\n\n')
    assert canonical_text_sha256(' a\t\n') != canonical_text_sha256('a\n')
    assert canonical_text_bytes('\ufeffé\r\n') == '\ufeffé\n'.encode('utf-8')
    with pytest.raises(UnicodeDecodeError):
        canonical_text_sha256(b'\xff')


@pytest.fixture
def isolated_resource(tmp_path, monkeypatch):
    resources = tmp_path / 'resources'
    resources.mkdir()
    payload = (RESOURCE / 'evidence_drug_target_index_v1.jsonl').read_bytes()
    manifest = (RESOURCE / 'evidence_drug_target_index_v1.manifest.json').read_bytes()
    index = resources / 'evidence_drug_target_index_v1.jsonl'
    index.write_bytes(payload)
    (resources / 'evidence_drug_target_index_v1.manifest.json').write_bytes(manifest)
    monkeypatch.setattr(verifier, '__file__', str(tmp_path / 'enrichment/document_verification.py'))
    verifier._lineage_index.cache_clear()
    yield index, payload
    verifier._lineage_index.cache_clear()


@pytest.mark.parametrize('mutation', ['drug_id', 'candidate_id', 'remove', 'add', 'reorder'])
def test_content_mutations_change_digest_and_fail_closed(isolated_resource, mutation):
    index, original = isolated_resource
    rows = [json.loads(line) for line in original.splitlines()]
    if mutation == 'drug_id':
        rows[0]['linked_drugs'][0]['id'] += '-changed'
    elif mutation == 'candidate_id':
        rows[0]['candidate_id'] += '-changed'
    elif mutation == 'remove':
        rows.pop()
    elif mutation == 'add':
        rows.append(rows[0])
    else:
        rows[0], rows[1] = rows[1], rows[0]
    changed = ('\n'.join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')) for row in rows) + '\n').encode('utf-8')
    assert canonical_text_sha256(changed) != canonical_text_sha256(original)
    index.write_bytes(changed)
    assert verifier._lineage_index() == {}


@pytest.mark.parametrize('failure', ['missing', 'invalid_json', 'invalid_utf8', 'unknown_contract',
                                      'manifest_not_object', 'invalid_row', 'invalid_candidate_id'])
def test_invalid_resources_fail_closed(isolated_resource, failure):
    index, _ = isolated_resource
    manifest_path = index.with_suffix('.manifest.json')
    if failure == 'missing':
        index.unlink()
    elif failure == 'invalid_utf8':
        index.write_bytes(b'\xff')
    else:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if failure == 'manifest_not_object':
            manifest = []
        elif failure in {'invalid_row', 'invalid_candidate_id'}:
            rows = [json.loads(line) for line in index.read_bytes().splitlines()]
            if failure == 'invalid_row':
                rows[0] = 1
            else:
                rows[0]['candidate_id'] = []
            index.write_bytes(('\n'.join(json.dumps(row) for row in rows) + '\n').encode('utf-8'))
            manifest['index_sha256'] = canonical_text_sha256(index.read_bytes())
        elif failure == 'invalid_json':
            index.write_bytes(b'{invalid}\n')
            manifest['index_sha256'] = canonical_text_sha256(index.read_bytes())
        else:
            manifest['digest_contract'] = 'unknown-contract'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    assert verifier._lineage_index() == {}


def test_real_git_export_retains_index_and_frozen_predictions(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / '.gitattributes').write_bytes(b'* text eol=lf\n')
    resources = repo / 'resources'
    resources.mkdir()
    original = (RESOURCE / 'evidence_drug_target_index_v1.jsonl').read_bytes()
    (resources / 'evidence_drug_target_index_v1.jsonl').write_bytes(
        canonical_text_bytes(original).replace(b'\n', b'\r\n'))
    (resources / 'evidence_drug_target_index_v1.manifest.json').write_bytes(
        (RESOURCE / 'evidence_drug_target_index_v1.manifest.json').read_bytes())
    project = RESOURCE.parents[2]
    prediction = project / 'evaluation/verification_chain/verifier_freeze_closure/heldout_annotation/unlabeled_model_probe.jsonl'
    frozen = prediction.read_bytes()
    (repo / 'predictions.jsonl').write_bytes(frozen)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True)
    tree = subprocess.check_output(['git', 'write-tree'], cwd=repo, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', '--format=zip', tree], cwd=repo)
    export = tmp_path / 'export'
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        bundle.extractall(export)
    index_name = 'resources/evidence_drug_target_index_v1.jsonl'
    blob = subprocess.check_output(['git', 'show', f'{tree}:{index_name}'], cwd=repo)
    exported = (export / index_name).read_bytes()
    assert canonical_text_sha256(original) == canonical_text_sha256(blob) == canonical_text_sha256(exported)
    assert [json.loads(line) for line in original.splitlines()] == [json.loads(line) for line in exported.splitlines()]
    exported_predictions = (export / 'predictions.jsonl').read_bytes()
    assert canonical_text_sha256(frozen) == canonical_text_sha256(exported_predictions)
    assert len(exported_predictions.splitlines()) == 12
    assert [json.loads(line) for line in frozen.splitlines()] == [json.loads(line) for line in exported_predictions.splitlines()]
    assert CANONICAL_TEXT_DIGEST_VERSION == 'canonical-text-sha256/1.0'
    monkeypatch.setattr(verifier, '__file__', str(export / 'enrichment/document_verification.py'))
    verifier._lineage_index.cache_clear()
    try:
        assert len(verifier._lineage_index()) == 3347
    finally:
        verifier._lineage_index.cache_clear()


def test_real_index_loads_with_lf_export(tmp_path, monkeypatch):
    resources = tmp_path / 'resources'
    resources.mkdir()
    payload = (RESOURCE / 'evidence_drug_target_index_v1.jsonl').read_bytes()
    lf = payload.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    (resources / 'evidence_drug_target_index_v1.jsonl').write_bytes(lf)
    (resources / 'evidence_drug_target_index_v1.manifest.json').write_bytes(
        (RESOURCE / 'evidence_drug_target_index_v1.manifest.json').read_bytes())
    monkeypatch.setattr(verifier, '__file__', str(tmp_path / 'enrichment/document_verification.py'))
    verifier._lineage_index.cache_clear()
    try:
        assert len(verifier._lineage_index()) == 3347
    finally:
        verifier._lineage_index.cache_clear()
