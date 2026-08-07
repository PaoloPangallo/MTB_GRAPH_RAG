"""Probe A — Reachability statica dei moduli Python del repository.

Costruisce il grafo degli import con l'AST (nessun import eseguito, nessun side
effect) e classifica ogni modulo in base a CHI lo raggiunge:

  CANONICAL_RUNTIME            raggiungibile da backend.api.main
  SHADOW_EVALUATION            raggiungibile solo da evaluation/ o scripts/
  LEGACY_RETAINED_FOR_EXPERIMENT  raggiungibile solo da benchmark/comparison/...
  TEST_ONLY                    raggiungibile solo dai test
  DEAD_OR_UNREACHABLE          nessun entrypoint lo raggiunge

Output: CSV su stdout.
"""
from __future__ import annotations

import ast
import csv
import sys
from collections import deque
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()  # mtb-graphrag


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def collect_modules() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in ROOT.rglob("*.py"):
        s = str(p)
        if "__pycache__" in s or "node_modules" in s or ".venv" in s:
            continue
        out[module_name(p)] = p
    return out


def imports_of(path: Path, self_mod: str) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    pkg = self_mod.rsplit(".", 1)[0] if "." in self_mod else ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative
                base = pkg
                for _ in range(node.level - 1):
                    base = base.rsplit(".", 1)[0] if "." in base else ""
                mod = f"{base}.{node.module}" if node.module else base
            else:
                mod = node.module or ""
            if mod:
                found.add(mod)
                for a in node.names:
                    found.add(f"{mod}.{a.name}")
    return found


def main() -> None:
    modules = collect_modules()
    names = set(modules)
    graph: dict[str, set[str]] = {}
    for mod, path in modules.items():
        raw = imports_of(path, mod)
        edges = set()
        for r in raw:
            if r in names:
                edges.add(r)
            else:  # from pkg.mod import symbol -> pkg.mod
                parent = r.rsplit(".", 1)[0]
                if parent in names:
                    edges.add(parent)
        graph[mod] = edges

    def reach(seeds: list[str]) -> set[str]:
        seen, q = set(), deque(s for s in seeds if s in names)
        seen.update(q)
        while q:
            cur = q.popleft()
            for nxt in graph.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        return seen

    api = reach(["backend.api.main"])
    research_api = reach(["backend.api.research_routes"])
    legacy_api = reach(["backend.api.routes"])
    evaluation = reach([m for m in names if m.startswith("evaluation.") and not m.startswith("evaluation.tests")])
    scripts = reach([m for m in names if m.startswith("scripts.")])
    tests = reach([m for m in names if ".tests" in m or m.startswith("evaluation.tests")
                   or "/test_" in m or m.rsplit(".", 1)[-1].startswith("test_")])

    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["module", "path", "loc", "classification",
                "reached_by_api_main", "reached_by_research_api", "reached_by_legacy_api",
                "reached_by_evaluation", "reached_by_scripts", "reached_by_tests"])
    for mod in sorted(names):
        path = modules[mod]
        loc = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        in_api, in_res, in_leg = mod in api, mod in research_api, mod in legacy_api
        in_ev, in_sc, in_te = mod in evaluation, mod in scripts, mod in tests
        is_test = mod.rsplit(".", 1)[-1].startswith("test_") or ".tests" in mod
        if is_test:
            cls = "TEST_CODE"
        elif in_res:
            cls = "CANONICAL_RUNTIME"
        elif in_api and in_leg:
            cls = "LEGACY_RETAINED_FOR_EXPERIMENT"
        elif in_api:
            cls = "CANONICAL_RUNTIME"
        elif in_ev or in_sc:
            cls = "SHADOW_EVALUATION"
        elif in_te:
            cls = "TEST_ONLY"
        else:
            cls = "DEAD_OR_UNREACHABLE"
        w.writerow([mod, str(path.relative_to(ROOT)).replace("\\", "/"), loc, cls,
                    in_api, in_res, in_leg, in_ev, in_sc, in_te])


if __name__ == "__main__":
    main()
