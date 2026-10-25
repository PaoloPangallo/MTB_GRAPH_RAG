import { describe, expect, it } from 'vitest';
import { apiUrl } from './apiBase';

describe('apiUrl', () => {
  it('preserves the configured backend origin for legacy API paths', () => {
    expect(apiUrl('/api/v1/analyze', 'http://127.0.0.1:8010')).toBe(
      'http://127.0.0.1:8010/api/v1/analyze',
    );
  });

  it('does not produce a double slash when the configured origin ends with one', () => {
    expect(apiUrl('/api/v1/subgraph', 'https://api.example.test/')).toBe(
      'https://api.example.test/api/v1/subgraph',
    );
  });
});
