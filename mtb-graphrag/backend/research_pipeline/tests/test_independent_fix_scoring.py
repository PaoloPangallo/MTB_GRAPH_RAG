import importlib.util
from pathlib import Path
import pytest


def test_missing_human_gold_stays_pending():
    root = Path(__file__).resolve().parents[4]
    source = root / 'experiments_real/sourceunit_fix_evaluation/score.py'
    if not source.is_file():
        pytest.skip('Optional independent evaluation archive is not installed')
    spec = importlib.util.spec_from_file_location('fix_scoring', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = [{'item_id': 'x', 'prediction': 'CORRECT'}]
    assert module.score(records, [])['accuracy'] is None
    assert module.score(records, [{'item_id': 'x', 'label': 'CORRECT', 'adjudicated': True,
                                    'origin': 'MODEL_OUTPUT'}])['status'] == 'PENDING'
