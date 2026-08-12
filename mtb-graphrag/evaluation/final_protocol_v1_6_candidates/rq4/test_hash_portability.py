from __future__ import annotations

import json
from pathlib import Path
import subprocess
import shutil
import tempfile

from hash_h01 import digest, manifest_entries


ROOT = Path(__file__).parent
POLICY = json.loads((ROOT / "normative_hash_policy.json").read_text(encoding="utf-8"))


def test_manifest_paths_are_repository_relative_and_portable():
    entries = manifest_entries(POLICY["normative_files"])
    assert entries
    assert all(not Path(entry["path"]).is_absolute() for entry in entries)
    assert all(":" not in entry["path"] for entry in entries)
    assert all("\\" not in entry["path"] for entry in entries)


def test_normative_digest_is_stable_across_repeated_builds():
    assert digest(POLICY["normative_files"]) == digest(POLICY["normative_files"])


def test_builder_is_independent_of_cwd():
    script = ROOT / "hash_h01.py"
    first = subprocess.check_output(["python", str(script)], cwd=ROOT, text=True)
    second = subprocess.check_output(["python", str(script)], cwd=ROOT.parent.parent.parent, text=True)
    assert json.loads(first) == json.loads(second)


def test_tampered_normative_bytes_change_identity_without_touching_repo():
    with tempfile.TemporaryDirectory(dir=r"C:\tmp") as temp:
        repo = Path(temp) / "repo"
        copied = repo / "mtb-graphrag" / "evaluation" / "final_protocol_v1_6_candidates" / "rq4"
        copied.parent.mkdir(parents=True)
        shutil.copytree(ROOT, copied)
        target = copied / POLICY["normative_files"][0]
        target.write_bytes(target.read_bytes() + b"x")
        assert digest(POLICY["normative_files"], artifact_root=copied, repo_root=repo) != digest(POLICY["normative_files"])


def test_tampered_support_bytes_change_support_identity_without_touching_repo():
    with tempfile.TemporaryDirectory(dir=r"C:\tmp") as temp:
        repo = Path(temp) / "repo"
        copied = repo / "mtb-graphrag" / "evaluation" / "final_protocol_v1_6_candidates" / "rq4"
        copied.parent.mkdir(parents=True)
        shutil.copytree(ROOT, copied)
        target = copied / "test_vectors.json"
        target.write_bytes(target.read_bytes() + b"x")
        assert digest(POLICY["support_files"], artifact_root=copied, repo_root=repo) != digest(POLICY["support_files"])
