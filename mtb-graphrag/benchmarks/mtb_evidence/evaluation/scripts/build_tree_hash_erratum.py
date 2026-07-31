"""Costruisce l'erratum degli hash di albero dipendenti dalle fini riga.

Terzo erratum, e il terzo fatto distinto:

    artifact_hash_erratum          l'impronta di un **file** fu presa in una
                                   forma di byte che un checkout pulito non
                                   riproduce
    generator_provenance_erratum   un artefatto registra l'impronta del
                                   **generatore** che lo produsse, e quel
                                   generatore e' cambiato dopo
    tree_hash_erratum              l'impronta di una **directory** fu presa su
                                   un albero i cui file erano CRLF sul disco

Il terzo non e' il primo ripetuto: un albero ha proprieta' che un file non ha —
quali file lo compongono, in che ordine, e quali sono testo. La discovery e' per
questo diversa, e la registrazione anche.

## Come la classificazione testo/binario e' determinata

Da `git check-attr text`, cioe' dalla stessa dichiarazione che governa il
checkout, mai da un'euristica sui byte. Il risultato viene **registrato**
nell'erratum path per path, insieme a: da dove viene (`classification_source`),
a quale revisione (`classification_commit`), quali `.gitattributes` l'hanno
determinata (`gitattributes_paths`) e con quale impronta (`gitattributes_sha256`).

Registrarla e' cio' che rende l'erratum verificabile in un archivio estratto,
che `git` non ce l'ha. E `gitattributes_sha256` e' cio' che permette di
accorgersi che la regola da cui deriva e' cambiata, invece di scoprirlo quando
un hash smette di tornare.

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_tree_hash_erratum
    python -m ... --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.pipeline.evidence.integrity import hash_policy as FILE_POLICY  # noqa: E402
from backend.pipeline.evidence.integrity import tree_hash_policy as TREE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
GIT_ROOT = REPO_ROOT.parent
PACKAGE_PREFIX = "mtb-graphrag/"

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "tree_hash_erratum.json"
)

SCHEMA_VERSION = "tree_hash_erratum/1.0"
PHASE = "hermetic-reproducibility-closure/1.0"

FROZEN_REVISION = "b6694ba23d189b17a9ca87a5a3e86990db4445a8"

# L'unica esclusione, e dichiarata: `sha256_tree` la applica da sempre, e
# `__pycache__` non e' contenuto del repository.
EXCLUDE = ("__pycache__",)

# I `.gitattributes` che determinano la classificazione, in ordine di
# precedenza crescente: l'annidato vince sul primo.
GITATTRIBUTES = (
    ".gitattributes",
    "mtb-graphrag/benchmarks/.gitattributes",
)

# Ruolo -> directory, come i tre artefatti congelati li nominano. L'elenco e'
# quello dei ruoli **dichiarati**, non quello dei ruoli divergenti: quali
# divergano lo decide la misura, non questa tabella.
ROLES = {
    "adjudication": "benchmarks/mtb_evidence/v3/multi_intervention_adjudication",
    "disease hierarchy policy": "benchmarks/mtb_evidence/v3/disease_hierarchy_policy",
    "pre-promotion audit 1.3": "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3",
    "shadow repository 1.0": "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
    "shadow repository 1.1": "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
    "shadow repository 1.2": (
        "benchmarks/mtb_evidence/v3/diagnostic_disease_scope_narrowing_shadow"
    ),
    "shadow repository 1.3": "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3",
    "shadow repository 1.4": "benchmarks/mtb_evidence/v3/pre_promotion_required_fixes_1_4",
    "terminology closure": "benchmarks/mtb_evidence/v3/terminology_mapping_closure",
}

# Gli artefatti che dichiarano un blocco `frozen_tree_sha256`, con il percorso
# del blocco. Sono i tre trovati dalla scansione, nominati perche' l'erratum
# possa dire *chi* registra un'impronta invece di lasciarlo dedurre.
DECLARING_ARTIFACTS = (
    (
        "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3/audit_manifest.json",
        ("integrity", "frozen_tree_sha256"),
    ),
    (
        "benchmarks/mtb_evidence/v3/pre_promotion_required_fixes_1_4/"
        "repository_v1_4_manifest.json",
        ("integrity", "frozen_tree_sha256"),
    ),
    (
        "benchmarks/mtb_evidence/v3/prototype_corpus_promotion_1_4/"
        "operational_integrity.json",
        ("frozen_tree_sha256",),
    ),
)

# Il test che verifica ciascun artefatto dichiarante. `recorded_by_tests` di un
# albero si deriva da qui attraverso `recorded_by_artifacts`, invece di essere
# scritto a mano: un elenco compilato a memoria e' precisamente cio' che questa
# fase ha gia' trovato sbagliato due volte.
#
# `test_author_approval_23344087` non compare, ed e' una constatazione misurata:
# non usa `sha256_tree`. Le sue tre failure sono impronte **di file**, coperte
# da `artifact_hash_erratum` e chiuse la' — dare loro il reason code di albero
# significherebbe classificarle sotto una causa che non e' la loro.
VERIFIED_BY = {
    "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3/audit_manifest.json": (
        "backend/tests/test_pre_promotion_audit_1_3.py::IntegrityTests"
        "::test_the_current_hashes_still_match_the_recorded_ones"
    ),
    "benchmarks/mtb_evidence/v3/pre_promotion_required_fixes_1_4/"
    "repository_v1_4_manifest.json": (
        "backend/tests/test_pre_promotion_required_fixes_1_4.py::IntegrityTests"
        "::test_the_shadow_repositories_are_unchanged"
    ),
    "benchmarks/mtb_evidence/v3/prototype_corpus_promotion_1_4/"
    "operational_integrity.json": (
        "backend/tests/test_prototype_corpus_promotion_1_4.py"
        "::OperationalIntegrityTests::test_the_shadow_repositories_are_unchanged"
    ),
}

_TIMEOUT_SECONDS = 180


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=GIT_ROOT,
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
    ).stdout


def classify(relative_paths: list[str]) -> dict[str, bool]:
    """path -> e' testo, secondo `git check-attr text`.

    Non un'euristica sui byte: la stessa dichiarazione che governa il checkout.
    `text: set` o `text: auto` significa testo; `unset` o `false` significa
    binario.
    """
    payload = "\n".join(PACKAGE_PREFIX + path for path in relative_paths)
    out = subprocess.run(
        ["git", "check-attr", "--stdin", "text"],
        cwd=GIT_ROOT,
        input=payload.encode(),
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
    ).stdout.decode()

    classification: dict[str, bool] = {}
    for line in out.splitlines():
        if line.count(": ") < 2:
            continue
        path, _attr, value = line.rsplit(": ", 2)
        classification[path.removeprefix(PACKAGE_PREFIX)] = value.strip() not in (
            "unset",
            "false",
        )
    return classification


def declared_tree_hashes() -> dict[str, dict[str, list[str]]]:
    """ruolo -> impronta storica -> artefatti che la dichiarano."""
    declared: dict[str, dict[str, list[str]]] = {}
    for artifact, trail in DECLARING_ARTIFACTS:
        payload = json.loads((REPO_ROOT / artifact).read_text(encoding="utf-8"))
        for key in trail:
            payload = payload[key]
        for role, digest in payload.items():
            declared.setdefault(role, {}).setdefault(digest, []).append(artifact)
    return declared


def _clean_checkout_legacy_tree_sha256(root: Path, text_files: set[str]) -> str:
    """L'impronta che `sha256_tree` darebbe su un checkout pulito.

    Stesso algoritmo di `SCOPE.sha256_tree` — righe `path:hash` ordinate,
    unite da newline — ma sui byte che un checkout pulito scriverebbe: LF per i
    file testuali. Serve a rispondere «questo albero e' riproducibile altrove?»
    senza dover avere altrove sotto mano, e dando la stessa risposta ovunque il
    generatore giri.

    L'erratum delle impronte di file resta applicato: per gli otto sorgenti che
    registra, un checkout pulito produce comunque il valore storico, perche' e'
    quello che `sha256_file` restituisce.
    """
    from benchmarks.mtb_evidence.evaluation import legacy_hash_erratum as FILE_ERRATUM

    rows = []
    for item in sorted(root.rglob("*")):
        if not item.is_file() or any(part in EXCLUDE for part in item.parts):
            continue
        relative = item.relative_to(root).as_posix()
        if FILE_ERRATUM.is_registered(item):
            digest = FILE_ERRATUM.recorded_sha256(item)
        elif relative in text_files:
            digest = FILE_POLICY.canonical_lf_sha256(item)
        else:
            digest = FILE_POLICY.raw_sha256(item)
        rows.append(f"{relative}:{digest}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def build() -> dict[str, Any]:
    from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE

    declared = declared_tree_hashes()
    gitattributes = {
        path: FILE_POLICY.canonical_lf_sha256(GIT_ROOT / path)
        for path in GITATTRIBUTES
    }
    # Non HEAD: l'ultimo commit che ha toccato i `.gitattributes` da cui la
    # classificazione deriva. HEAD renderebbe l'erratum stale a ogni commit,
    # anche a quelli che con la classificazione non c'entrano niente — e un
    # erratum che va rigenerato di continuo smette di essere letto.
    classification_commit = (
        _git("log", "-1", "--format=%H", "--", *GITATTRIBUTES).decode().strip()
    )

    trees = []
    for role in sorted(ROLES):
        if role not in declared:
            continue
        relative = ROLES[role]
        root = REPO_ROOT / relative

        historical_values = sorted(declared[role])
        if len(historical_values) != 1:
            raise RuntimeError(
                f"{role} e' dichiarato con {len(historical_values)} impronte "
                f"storiche diverse: {historical_values}. L'erratum assume una "
                f"forma storica sola per albero."
            )
        historical = historical_values[0]

        files = [relative for relative, _ in TREE.enumerate_files(root, exclude=EXCLUDE)]
        is_text = classify([f"{relative}/{name}" for name in files])
        text_files = sorted(
            name for name in files if is_text.get(f"{relative}/{name}", False)
        )
        binary_files = sorted(set(files) - set(text_files))

        canonical = TREE.canonical_tree_sha256(
            root, text_files=text_files, exclude=EXCLUDE, require_declared=False
        )

        # Riproducibile **da un checkout pulito**, non «in questo ambiente».
        # Misurarlo con `SCOPE.sha256_tree` direbbe soltanto come sono le fini
        # riga sul disco di chi esegue il generatore: sulla macchina che ha
        # congelato queste impronte tornerebbero tutte, ed e' esattamente
        # l'illusione da cui nasce l'intero difetto.
        reproducible = _clean_checkout_legacy_tree_sha256(root, set(text_files)) == (
            historical
        )

        affected = _affected_paths(root, files, set(text_files))

        record = TREE.TreeHashRecord(
            tree_root=relative,
            historical_raw_tree_sha256=historical,
            canonical_lf_tree_sha256=canonical,
            file_count=len(files),
            affected_text_file_count=len(affected),
            affected_paths=tuple(affected),
        )
        trees.append(
            {
                **record.as_dict(),
                "binary_files": binary_files,
                "classification_commit": classification_commit,
                "classification_source": "git check-attr text",
                "current_reproducibility_status": (
                    "reproducible_from_a_clean_checkout"
                    if reproducible
                    else "not_reproducible_from_a_clean_checkout"
                ),
                "gitattributes_paths": list(GITATTRIBUTES),
                "gitattributes_sha256": gitattributes,
                "historical_commit": FROZEN_REVISION,
                "historical_form": "crlf_on_disk",
                "recorded_by_artifacts": sorted(declared[role][historical]),
                "recorded_by_tests": sorted(
                    VERIFIED_BY[artifact] for artifact in declared[role][historical]
                ),
                "role": role,
                "text_files": text_files,
            }
        )

    diverging = [tree for tree in trees if tree["affected_text_file_count"]]
    return {
        "counts": {
            "affected_files": sum(t["affected_text_file_count"] for t in diverging),
            "declared_trees": len(trees),
            "diverging_trees": len(diverging),
        },
        "exclude": list(EXCLUDE),
        "hash_policy_version": TREE.POLICY_VERSION,
        "normalization": TREE.NORMALIZATION,
        "phase": PHASE,
        "schema_version": SCHEMA_VERSION,
        "trees": trees,
    }


def _affected_paths(root: Path, files: list[str], text_files: set[str]) -> list[str]:
    """I file testuali che sul disco hanno CRLF.

    Sono quelli per cui la forma su disco e quella canonica differiscono, cioe'
    quelli che rendono l'impronta storica di questo albero irriproducibile
    altrove. Misurati, non elencati.
    """
    affected = []
    for name in files:
        if name not in text_files:
            continue
        data = (root / name).read_bytes()
        if b"\r\n" in data:
            affected.append(name)
    return sorted(affected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    erratum = build()
    rendered = json.dumps(erratum, ensure_ascii=False, indent=2, sort_keys=True)

    if args.check:
        if not ERRATUM_PATH.exists():
            print(f"erratum assente: {ERRATUM_PATH}", file=sys.stderr)
            return 1
        if ERRATUM_PATH.read_text(encoding="utf-8").rstrip("\n") != rendered:
            print("l'erratum non corrisponde agli alberi correnti", file=sys.stderr)
            return 1
        print(json.dumps(erratum["counts"], indent=2, sort_keys=True))
        return 0

    ERRATUM_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERRATUM_PATH.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(f"scritto {ERRATUM_PATH.relative_to(REPO_ROOT)}")
    print(json.dumps(erratum["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
