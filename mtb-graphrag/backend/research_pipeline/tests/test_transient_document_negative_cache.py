"""Transient transport failures expire; missing documents and evidence do not."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from backend.research_pipeline.documents import authorized_cache as module
from backend.research_pipeline.documents.live_resolution import resolve_live_documents

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc).timestamp()


def seed(cache, *, availability='RESOLUTION_FAILED', age=7200, kind='transient', status=None):
    attempt = {'kind': kind, 'url': 'https://eutils.ncbi.nlm.nih.gov/example'}
    if status is not None:
        attempt['status'] = status
    record = {'document_id': 'pmid:123', 'identifiers': {'pmid': '123'},
              'availability': availability, 'retrieved_at': datetime.fromtimestamp(
                  NOW-age, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              'resolution_attempts': [attempt], 'local_cache_path': None}
    cache._record(record)
    return cache.manifest_path.read_bytes()


def make_cache(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(module.time, 'time', lambda: NOW)
    return module.AuthorizedDocumentCache(tmp_path, **kwargs)


def failed_request(url):
    return None, {'kind': 'transient', 'url': url, 'error': 'DNS failure'}


def test_stale_dns_failure_revalidates_once_and_preserves_history(tmp_path, monkeypatch):
    cache = make_cache(tmp_path, monkeypatch)
    before = seed(cache)
    cache._request = Mock(side_effect=failed_request)
    result = cache.resolve_pmid('123')
    assert cache._request.call_count == 2  # Existing bounded summary + abstract endpoints.
    assert cache.manifest_path.read_bytes().startswith(before)
    assert result['negative_cache_revalidation']['previous_record_sha256']
    assert result['negative_cache_revalidation']['ttl_seconds'] == 3600
    cache.resolve_pmid('123')
    assert cache._request.call_count == 2


@pytest.mark.parametrize('age,availability,kind,status,network', [
    (3599, 'RESOLUTION_FAILED', 'transient', None, True),
    (7200, 'PMID_NOT_FOUND', 'http', 404, True),
    (7200, 'RESOLUTION_FAILED', 'http', 404, True),
    (7200, 'RESOLUTION_FAILED', 'transient', None, False),
    (7200, 'ABSTRACT_AVAILABLE', 'transient', None, True),
])
def test_nonexpiring_snapshots_do_not_fetch(tmp_path, monkeypatch, age, availability, kind, status, network):
    cache = make_cache(tmp_path, monkeypatch, network=network)
    before = seed(cache, age=age, availability=availability, kind=kind, status=status)
    cache._request = Mock(side_effect=AssertionError('Unexpected fetch'))
    assert cache.resolve_pmid('123')['cache_hit'] is True
    cache._request.assert_not_called()
    assert cache.manifest_path.read_bytes() == before


@pytest.mark.parametrize('status', [408, 429, 500, 503])
def test_stale_transient_http_status_is_revalidated(tmp_path, monkeypatch, status):
    cache = make_cache(tmp_path, monkeypatch)
    seed(cache, kind='http', status=status)
    cache._request = Mock(side_effect=failed_request)
    cache.resolve_pmid('123')
    assert cache._request.call_count == 2


def test_one_resolution_per_document_across_candidates(tmp_path, monkeypatch):
    cache = make_cache(tmp_path, monkeypatch)
    seed(cache)
    cache._request = Mock(side_effect=failed_request)
    associations = [{'candidate_id': 'C'+str(i), 'available_bundles': [{
        'bundle_id': 'B'+str(i), 'document_id': 'pmid:123',
        'provenance_identifier': {'pmid': '123'}}]}
        for i in range(5)]
    result = resolve_live_documents(associations, cache, {})
    assert len(result.documents) == 5
    assert cache._request.call_count == 2
