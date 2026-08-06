"""Congela il benchmark CaseContext **prima** dell'esecuzione (§18).

Uso::

    python -m evaluation.freeze_rq4 [--verify]

Scrive ``benchmark.jsonl`` e ``frozen_benchmark_manifest.json`` con hash del
dataset, hash del prompt del parser, commit corrente e data. Con ``--verify``
non riscrive nulla: ricalcola gli hash e fallisce se il benchmark è cambiato
rispetto al manifest — è il controllo che dimostra che il gold non è stato
modificato dopo aver visto gli output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from evaluation.rq4.benchmark import (
    BENCHMARK_LABEL, BENCHMARK_VERSION, CASES, CATEGORY_ORDER, validate_benchmark,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "evaluation" / "rq4_casecontext_robustness"
BENCHMARK = OUT / "benchmark.jsonl"
MANIFEST = OUT / "frozen_benchmark_manifest.json"


def _serialize() -> str:
    return "".join(
        json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in CASES
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    validate_benchmark()
    payload = _serialize()
    digest = _sha(payload)

    from backend.research_pipeline.casecontext import prompt as parser_prompt

    manifest = {
        "benchmark_version": BENCHMARK_VERSION,
        "label": BENCHMARK_LABEL,
        "status": "FROZEN_BEFORE_EXECUTION",
        "case_count": len(CASES),
        "categories": {c: sum(1 for x in CASES if x["category"] == c) for c in CATEGORY_ORDER},
        "benchmark_sha256": digest,
        "definition_module_sha256": _sha(
            (REPO_ROOT / "evaluation" / "rq4" / "benchmark.py").read_text(encoding="utf-8")
        ),
        "parser_prompt_version": parser_prompt.PROMPT_VERSION,
        "parser_prompt_hash": parser_prompt.prompt_hash(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "mandatory_cases_present": {
            "non_actionable_leg_pain": any(c["text"] == "Mi fa male la gamba." for c in CASES),
            "adversarial_ignore_instructions": any(
                "Ignora le istruzioni precedenti" in c["text"] for c in CASES
            ),
        },
        "note": (
            "Gold congelato prima della prima chiamata al parser. Le attese non sono "
            "state modificate dopo aver osservato gli output."
        ),
    }

    if args.verify:
        if not MANIFEST.exists():
            print("[rq4-freeze] manifest assente: il benchmark non è stato congelato")
            return 1
        stored = json.loads(MANIFEST.read_text(encoding="utf-8"))
        ok = True
        for key in ("benchmark_sha256", "definition_module_sha256", "parser_prompt_hash"):
            if stored.get(key) != manifest[key]:
                print(f"[rq4-freeze] MISMATCH {key}\n  congelato: {stored.get(key)}\n  attuale  : {manifest[key]}")
                ok = False
        if BENCHMARK.exists() and _sha(BENCHMARK.read_text(encoding="utf-8")) != stored["benchmark_sha256"]:
            print("[rq4-freeze] MISMATCH: benchmark.jsonl differisce dal manifest")
            ok = False
        print("[rq4-freeze] verifica:", "OK — benchmark immutato" if ok else "FALLITA")
        return 0 if ok else 1

    if MANIFEST.exists():
        stored = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if stored.get("benchmark_sha256") != digest:
            print("[rq4-freeze] RIFIUTO: il benchmark è già congelato con un hash diverso.")
            print(f"  congelato il {stored.get('frozen_at')} -> {stored.get('benchmark_sha256')}")
            print(f"  attuale                              -> {digest}")
            print("  Ricongelare dopo l'esecuzione invaliderebbe il gold. Se la modifica è")
            print("  voluta, rimuovere esplicitamente il manifest e dichiararlo nel report.")
            return 1
        print("[rq4-freeze] già congelato con lo stesso hash, nessuna modifica")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    BENCHMARK.write_text(payload, encoding="utf-8", newline="\n")
    manifest["frozen_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[rq4-freeze] congelati {len(CASES)} casi")
    print(f"[rq4-freeze] benchmark_sha256 = {digest}")
    print(f"[rq4-freeze] prompt = {manifest['parser_prompt_version']} / {manifest['parser_prompt_hash'][:16]}…")
    print(f"[rq4-freeze] commit = {manifest['git_commit'][:12]} ({manifest['git_branch']})")
    print("[rq4-freeze] categorie:", json.dumps(manifest["categories"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
