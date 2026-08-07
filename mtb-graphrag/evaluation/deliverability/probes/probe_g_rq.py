"""Probe G — Riproducibilita' delle metriche RQ.

Riesegue gli script di evaluation REDIRIGENDO il loro OUT in una directory di
scratch, cosi' nessun artifact committato viene sovrascritto (§30). Poi confronta
il rigenerato con il committato, file per file.

Uso: probe_g_rq.py <repo_root> <scratch_out>
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
SCRATCH = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT))

SCRIPTS = [
    ("evaluation.run_rq1", "rq1_graph_candidate_fidelity"),
    ("evaluation.run_rq2", "rq2_pmid_associations"),
    ("evaluation.run_rq4", "rq4_casecontext_robustness"),
    ("evaluation.run_gca_v3_audit", "gca_v3"),
    ("evaluation.run_runtime_v3_integration", "runtime_v3_integration"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    report = []
    for modname, committed_dirname in SCRIPTS:
        out = SCRATCH / committed_dirname
        out.mkdir(parents=True, exist_ok=True)
        entry = {"script": modname, "committed_dir": f"evaluation/{committed_dirname}"}
        try:
            mod = importlib.import_module(modname)
            original = getattr(mod, "OUT", None)
            setattr(mod, "OUT", out)
            sys.argv = [modname]
            rc = mod.main()
            setattr(mod, "OUT", original)
            entry["exit_code"] = rc
            entry["ran"] = True
        except SystemExit as exc:
            entry["exit_code"] = exc.code
            entry["ran"] = True
        except Exception as exc:  # noqa: BLE001
            entry["ran"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"

        committed = ROOT / "evaluation" / committed_dirname
        regenerated = {p.name: sha(p) for p in sorted(out.glob("*")) if p.is_file()}
        original_files = {p.name: sha(p) for p in sorted(committed.glob("*")) if p.is_file()}
        entry["regenerated_files"] = len(regenerated)
        entry["committed_files"] = len(original_files)
        entry["identical"] = sorted(n for n in regenerated if original_files.get(n) == regenerated[n])
        entry["different"] = sorted(n for n in regenerated if n in original_files
                                    and original_files[n] != regenerated[n])
        entry["only_committed"] = sorted(set(original_files) - set(regenerated))
        entry["only_regenerated"] = sorted(set(regenerated) - set(original_files))
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    (SCRATCH / "_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                          encoding="utf-8")


if __name__ == "__main__":
    main()
