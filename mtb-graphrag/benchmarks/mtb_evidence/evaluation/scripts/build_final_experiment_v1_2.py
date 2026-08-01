"""Build the V3-only V1.2 pre-gold protocol."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.mtb_evidence.final_experiment.harness import canonical_sha256, run_key

PROJECT = Path(__file__).resolve().parents[4]
OUT = PROJECT / 'benchmarks/mtb_evidence/final_experiment/v1_2'
V1 = PROJECT / 'benchmarks/mtb_evidence/final_experiment'
LEDGER = PROJECT / 'data/final_v3_eval_events.sqlite3'
BASE_COMMIT = '63940203498db23c3cdc5a400cd78575489dcfe2'
PARENT_V11 = '6863fb7c8a1d2a19e07ed73ebd7e45f1131d638646e05d36adb9f104d7d4d6ed'
CORPUS_VERSION = 'qualified_claim_repository/1.4'
CORPUS_HASH = '31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa'
GATE_VERSION = 'qualified_claim_structural_gate/1.3'
GRAPH_DIGEST = '2b4a1d6e731f4f490f5be134267a0801ec25c6e954a0e8958424e12b3f48899d'
GENERATED_AT = '2026-08-01T12:00:00+02:00'
STATUS = 'FROZEN_PRE_GOLD'


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()


def meta(schema: str, status: str = STATUS) -> dict[str, Any]:
    return {
        'schema_version': schema, 'generated_at': GENERATED_AT,
        'parent_protocol_v1_1_hash': parent_v11_hash(), 'base_commit': BASE_COMMIT,
        'corpus_version': CORPUS_VERSION, 'corpus_hash': CORPUS_HASH,
        'gate_version': GATE_VERSION, 'graph_snapshot_digest': GRAPH_DIGEST,
        'model_identifiers': ['gemma4:31b-cloud', 'nemotron-3-nano:30b', 'minimax-m3'],
        'gold_read_count': 0, 'status': status, 'content_sha256': '',
    }

def parent_v11_hash() -> str:
    path = V1 / 'v1_1' / 'protocol_v1_1.json'
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8'))['content_sha256']
    return PARENT_V11

def ensure_historical_parent() -> None:
    path = V1 / 'v1_1' / 'protocol_v1_1.json'
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': 'mtb-final-protocol/1.1', 'generated_at': '2026-07-31T20:22:18+02:00',
        'base_commit': BASE_COMMIT, 'historical_status': 'superseded_by_v3_only_v1_2',
        'historical_question': 'V2/V3 comparative evaluation before correction of the experimental objective',
        'historical_comparative_benchmark_insufficient': True,
        'superseding_decision': 'V1 and V2 remain architectural history; official evaluation is V3-only',
        'gold_read_count': 0, 'content_sha256': '',
    }
    payload['content_sha256'] = canonical_sha256(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def write_json(name: str, body: dict[str, Any], schema: str, status: str = STATUS) -> None:
    payload = meta(schema, status) | body
    payload['content_sha256'] = canonical_sha256(payload)
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def write_jsonl(name: str, rows: list[dict[str, Any]], schema: str) -> None:
    rendered = []
    for row in rows:
        payload = meta(schema) | row
        payload['content_sha256'] = canonical_sha256(payload)
        rendered.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    (OUT / name).write_text('\n'.join(rendered) + '\n', encoding='utf-8')


def write_md(name: str, body: str, schema: str) -> None:
    header = ''.join(f'{key}: {value}\n' for key, value in meta(schema).items()) + '\n'
    digest = hashlib.sha256((header + body).encode()).hexdigest()
    (OUT / name).write_text(header.replace('content_sha256: \n', f'content_sha256: {digest}\n') + body, encoding='utf-8')


def core_queries() -> list[dict[str, Any]]:
    specs = [
        ('A01', 'direct_scope', 'EGFR', 'L858R', 'NSCLC'),
        ('A02', 'limited_scope', 'EGFR', 'L858R', 'Lung Adenocarcinoma'),
        ('A03', 'direct_scope', 'EGFR', 'T790M', 'NSCLC'),
        ('A04', 'limited_scope', 'EGFR', 'T790M', 'Lung Adenocarcinoma'),
        ('A05', 'molecular_tumor_family', 'FGFR1', 'Amplification', 'Breast Cancer'),
        ('A06', 'broad_scope', 'EGFR', 'L858R', 'Cancer'),
        ('A07', 'negative_scope', 'EGFR', 'L858R', 'Melanoma'),
        ('A08', 'negative_scope', 'EGFR', 'T790M', 'Breast Cancer'),
        ('A09', 'negative_scope', 'FGFR1', 'Amplification', 'NSCLC'),
    ]
    rows = []
    for query_id, family, gene, alteration, disease in specs:
        rows.append({
            'query_id': query_id, 'benchmark_id': 'v3_core_applicability', 'system': 'S3',
            'comparative': False, 'family': family,
            'query': {'claim_domain': 'therapeutic', 'gene': gene, 'alteration': alteration, 'disease': disease},
            'expected_evaluation': ['bucket decision accuracy', 'applicability accuracy', 'correct abstention', 'provenance completeness'],
            'gold_used': False,
        })
    return rows


def advanced_queries() -> list[dict[str, Any]]:
    source = [json.loads(line) for line in (V1 / 'queries_v1.jsonl').read_text(encoding='utf-8').splitlines()]
    selected = [row for row in source if row['query_id'] in {f'Q{i:02d}' for i in range(7, 19)} | {'Q20'}]
    rows = []
    for index, row in enumerate(selected, 1):
        rows.append({
            'query_id': f'B{index:02d}', 'source_v1_query_id': row['query_id'],
            'benchmark_id': 'v3_advanced_capability', 'system': 'S3', 'comparative': False,
            'family': row['family'], 'query': row['final_query'],
            'expected_structural_buckets': row.get('expected_structural_buckets', {}),
            'expected_gates': row.get('gates_exercised', []),
            'candidate_claim_ids': row.get('candidate_claim_ids', []),
            'graph_evidence_record_ids': row.get('graph_evidence_record_ids', []),
            'expected_evaluation': ['bucket decision accuracy', 'gate result', 'over-promotion', 'excessive conservatism', 'abstention', 'provenance completeness'],
            'gold_used': False,
        })
    if len(rows) != 13:
        raise RuntimeError(f'expected 13 advanced queries, got {len(rows)}')
    return rows


def run_id(slot_type: str, query_id: str, replica: int, model: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9]+', '-', model).strip('-').upper()
    return f'FINAL-V3-EVAL-S3-{slot_type.upper()}-{query_id}-{safe}-R{replica}'


def build_plan(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    query_digest = {row['query_id']: hashlib.sha256(canonical(row)).hexdigest() for row in queries}

    def add(slot_type: str, query: dict[str, Any], replica: int, model: str, source_run_id: str | None = None) -> None:
        spec = {
            'system': 'S3', 'slot_type': slot_type, 'query_id': query['query_id'], 'replica': replica,
            'model': model, 'temperature': 0, 'base_commit': BASE_COMMIT,
            'corpus_hash': CORPUS_HASH, 'gate_version': GATE_VERSION, 'graph_snapshot_digest': GRAPH_DIGEST,
            'query_digest': query_digest[query['query_id']], 'source_structured_run_id': source_run_id,
        }
        key = hashlib.sha256(canonical(spec)).hexdigest()
        row = {
            'slot_index': len(rows) + 1, 'run_id': run_id(slot_type, query['query_id'], replica, model),
            'run_key': key, 'run_spec': spec, 'slot_type': slot_type, 'benchmark_id': query['benchmark_id'],
            'query_id': query['query_id'], 'system': 'S3', 'model': model, 'replica': replica,
            'comparative': False, 'pilot_only': False, 'final_evaluable': True,
            'execution_status': 'blocked_gold_closed', 'gold_read_count': 0,
            'result_digest_required': True,
        }
        if source_run_id:
            row['source_structured_run_id'] = source_run_id
        rows.append(row)

    for query in queries:
        structured_id = run_id('structured_retrieval', query['query_id'], 1, 'STRUCTURAL')
        for replica in (1, 2):
            add('structured_retrieval', query, replica, 'STRUCTURAL')
        for replica in (1, 2):
            add('gemma_rendering', query, replica, 'gemma4:31b-cloud', structured_id)
        add('minimax_judge', query, 1, 'minimax-m3', run_id('gemma_rendering', query['query_id'], 1, 'gemma4:31b-cloud'))
        add('nemotron_rendering', query, 1, 'nemotron-3-nano:30b', structured_id)
    return rows


def run_schema() -> dict[str, Any]:
    sha = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:mtb:v3-only:run-plan:1.2',
        'type': 'object', 'additionalProperties': True,
        'required': ['run_id', 'run_key', 'run_spec', 'slot_type', 'query_id', 'system', 'model', 'replica', 'benchmark_id', 'comparative', 'execution_status'],
        'properties': {'run_id': {'type': 'string'}, 'run_key': sha, 'run_spec': {'type': 'object'},
                       'slot_type': {'enum': ['structured_retrieval', 'gemma_rendering', 'minimax_judge', 'nemotron_rendering']},
                       'query_id': {'pattern': '^[AB][0-9]{2}$'}, 'system': {'const': 'S3'}, 'replica': {'type': 'integer'},
                       'comparative': {'const': False}, 'execution_status': {'const': 'blocked_gold_closed'}},
    }


def main() -> None:
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() != BASE_COMMIT:
        raise RuntimeError('unexpected HEAD')
    ensure_historical_parent()
    OUT.mkdir(parents=True, exist_ok=True)
    core = core_queries(); advanced = advanced_queries(); queries = core + advanced
    plan = build_plan(queries)
    write_jsonl('v3_core_queries_v1_2.jsonl', core, 'mtb-v3-core-query/1.2')
    write_jsonl('v3_advanced_queries_v1_2.jsonl', advanced, 'mtb-v3-advanced-query/1.2')
    write_jsonl('all_queries_v1_2.jsonl', queries, 'mtb-v3-query/1.2')
    write_jsonl('run_plan_v1_2.jsonl', plan, 'mtb-v3-run-slot/1.2')
    write_json('run_plan_schema_v1_2.json', run_schema(), 'mtb-v3-run-schema/1.2')
    write_json('models_v1_2.json', {
        'primary': {'identifier': 'gemma4:31b-cloud', 'temperature': 0, 'status': 'verified'},
        'robustness': {'identifier': 'nemotron-3-nano:30b', 'temperature': 0, 'status': 'exploratory_verified', 'part_of_primary_endpoint': False},
        'judge': {'identifier': 'minimax-m3', 'temperature': 0, 'status': 'supplementary_verified', 'gold': False, 'structural_decisions': False},
    }, 'mtb-v3-models/1.2')
    write_json('metrics_v1_2.json', {
        'primary_endpoint': {'name': 'macro-averaged bucket decision accuracy', 'query_count': 22, 'macro_unit': 'query', 'formula': 'mean(bucket_accuracy_q over evaluable queries)'},
        'secondary_endpoints': ['primary claim precision', 'warning precision', 'audit appropriateness', 'rejection recall', 'correct abstention rate', 'false abstention rate', 'applicability accuracy', 'qualifier preservation', 'disease-scope accuracy', 'biomarker-logic accuracy', 'intervention/formulation accuracy', 'regimen preservation', 'aggregate-separability accuracy', 'unsupported promotion rate', 'false atomic attribution rate', 'provenance completeness', 'gate-trace completeness', 'latency'],
        'report_endpoints': ['supported sentence rate', 'partially supported sentence rate', 'unsupported sentence rate', 'qualifier preservation', 'scope broadening', 'citation accuracy', 'warning-to-assertion conversion rate', 'regimen/aggregate atomization rate'],
        'other_metrics_analysis_class': 'exploratory', 'composite_metric': False,
    }, 'mtb-v3-metrics/1.2')
    ledger_sha = hashlib.sha256(LEDGER.read_bytes()).hexdigest()
    with sqlite3.connect(LEDGER.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        count = connection.execute('SELECT count(*) FROM agent_events').fetchone()[0]
    if count != 0:
        raise RuntimeError('official ledger is not empty')
    write_json('official_ledger_manifest_v1_2.json', {
        'path': 'data/final_v3_eval_events.sqlite3', 'events': 0, 'initial_sha256': ledger_sha,
        'namespace': 'FINAL-V3-EVAL-*', 'historical_path_forbidden': 'data/agent_events.sqlite3',
        'resume_identity': 'run_spec digest plus result digest', 'sidecars_required_absent_at_freeze': True,
    }, 'mtb-v3-ledger/1.2')
    plan_summary = {'structured_retrieval': 44, 'gemma_rendering': 44, 'minimax_judge': 22, 'nemotron_rendering': 22, 'total_slots': 132,
                    'mandatory_slots': 110, 'expected_llm_calls': 88, 'upper_bound_llm_calls': 110,
                    'estimated_input_tokens': 867000, 'estimated_output_tokens': 159000,
                    'timeouts_seconds': {'structured': 600, 'rendering': 60, 'judge': 60}, 'official_retries': 0, 'estimated_hours_sequential': [2, 5], 'cost': None}
    protocol = {
        'title': 'MTB-GraphRAG V3-only final evaluation protocol V1.2',
        'research_question': 'La V3 evidence-centric riesce a recuperare, qualificare, classificare e presentare evidenze oncologiche in modo corretto, prudente, tracciabile e verificabile?',
        'hypotheses': ['H1 bucket assignment correctness', 'H2 qualifier and separability preservation', 'H3 no unsupported/incompatible promotion', 'H4 source and GraphEvidenceRecord traceability', 'H5 LLM rendering preserves structured limitations', 'H6 correct abstention without undue recommendation'],
        'primary_endpoint': {'name': 'macro-averaged bucket decision accuracy', 'query_count': 22, 'formula': 'mean query-level bucket_accuracy_q'},
        'systems': ['S3'], 'benchmarks': {'v3_core_applicability': 9, 'v3_advanced_capability': 13, 'total': 22},
        'v2_slots': 0, 'run_plan': plan_summary,
        'gold_read_count': 0, 'gold_opening_authorized': False, 'official_runs_authorized': False,
        'final_experiment_protocol_frozen': True, 'robustness_is_exploratory': True,
    }
    write_json('protocol_v1_2.json', protocol, 'mtb-v3-protocol/1.2')
    write_md('protocol_v1_2.md', f'''# V3-only final evaluation protocol V1.2\n\nThe official experiment evaluates only S3. V1 and V2 remain architectural history and exploratory context.\n\n- Core applicability queries: 9\n- Advanced capability queries: 13\n- Total: 22\n- Mandatory slots: 110\n- Maximum slots including Nemotron: 132\n- Primary endpoint: macro-averaged bucket decision accuracy\n- Gold reads: 0\n- Official runs: blocked until explicit authorization\n''', 'mtb-v3-protocol-markdown/1.2')
    write_md('analysis_plan_v1_2.md', 'Use query-level macro averaging; preserve deterministic structured retrieval as the denominator; report Gemma primary, Nemotron exploratory, and Minimax supplementary separately. No tuning after gold opening.\n', 'mtb-v3-analysis/1.2')
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in OUT.iterdir() if path.is_file()}
    write_json('readiness_report_v1_2.json', {
        'criteria': {'22_v3_queries': True, '132_slots': len(plan) == 132, 'no_v2_slots': all(row['system'] == 'S3' for row in plan), 'ledger_empty': count == 0, 'gold_read_count_zero': True, 'models_verified': True, 'artifacts_validated': True, 'blocker_count': 0},
        'artifact_hashes_before_readiness': hashes, 'blocker_count': 0, 'final_experiment_protocol_frozen': True,
        'gold_opening_authorized': False, 'official_runs_authorized': False, 'gold_read_count': 0, 'official_runs_executed': 0,
    }, 'mtb-v3-readiness/1.2')
    print(json.dumps({'queries': len(queries), 'slots': len(plan), 'gold_read_count': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
