import hashlib
import json
from pathlib import Path


def test_protocol17_changes_only_operational_materialization():
    root = Path(__file__).parents[3]
    p17 = root / "evaluation" / "final_protocol_v1_7"
    amendment = json.loads((p17 / "operational_amendment.json").read_text(encoding="utf-8"))
    projection = json.loads((p17 / "scientific_projection.json").read_text(encoding="utf-8"))
    assert amendment["parent_protocol_sha256"] == "ac296a924a39b58caf3427f47153348566d21bcadb6fef94bfa8c6105400ac1d"
    assert amendment["operational_unit_count"] == 9
    assert amendment["operational_membership_unchanged"] is True
    assert amendment["expected_semantics_unchanged"] is True
    assert amendment["synthetic_clinical_queries"] == 0
    assert projection["counts"]["total"] == 222
    assert projection["counts"]["Operational"] == 9
    assert projection["unit_membership_unchanged"] is True
    assert projection["scientific_semantic_delta"] == 0


def test_protocol17_and_corpus_hashes_are_repeatable():
    root = Path(__file__).parents[3]
    p17 = root / "evaluation" / "final_protocol_v1_7"
    corpus = root / "research_frozen_artifacts" / "operational_v2"
    manifest = corpus / "operational_v2_manifest.json"
    manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    lines = [f"{p.relative_to(corpus).as_posix()}:{hashlib.sha256(p.read_bytes()).hexdigest()}"
             for p in sorted(corpus.rglob("*")) if p.is_file()]
    corpus_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    amendment = json.loads((p17 / "operational_amendment.json").read_text(encoding="utf-8"))
    assert manifest_hash == amendment["operational_manifest_sha256"]
    assert corpus_hash == amendment["operational_corpus_sha256"]

