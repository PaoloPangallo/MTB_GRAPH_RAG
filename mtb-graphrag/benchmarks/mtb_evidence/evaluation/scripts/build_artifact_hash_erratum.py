"""Costruisce l'erratum delle impronte dipendenti dalla fine riga.

Nessuna lista scritta a mano. Lo strumento indicizza ogni blob presente
nell'object database di git — quindi anche le forme storiche di un file, non
solo quella corrente — in tre forme (grezza, LF canonica, CRLF), poi cerca i
letterali a 64 esadecimali dentro ogni artefatto testuale tracciato. Cio' che
emerge e' l'insieme reale delle referenze non riproducibili, non quello che
qualcuno ricordava.

La differenza non e' accademica: le due costanti scritte a mano che questo
erratum sostituisce coprivano 10 referenze su 26 e omettevano due sorgenti
interi. Una lista di eccezioni compilata a memoria diventa una lista di cose
vere una volta sola.

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_artifact_hash_erratum
    python -m ... --check     # non riscrive: fallisce se l'erratum e' stale

I file binari sono esclusi: `artifact_hash_policy/2.0` normalizza il testo, e
per un `.xlsx` l'impronta corretta e' quella dei byte grezzi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.pipeline.evidence.integrity import hash_policy as POLICY  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
GIT_ROOT = REPO_ROOT.parent
PACKAGE_PREFIX = "mtb-graphrag/"

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "artifact_hash_erratum.json"
)

SCHEMA_VERSION = "artifact_hash_erratum/1.0"
PHASE = "hermetic-reproducibility-closure/1.0"

# Gli artefatti che possono citare un'impronta. Un `.py` non e' un artefatto: se
# un sorgente contiene un digest lo contiene come codice, e non e' una promessa
# congelata su un altro file.
ARTIFACT_SUFFIXES = (".json", ".jsonl", ".md", ".csv")

_HEX64 = re.compile(rb"\b[0-9a-f]{64}\b")
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

_TIMEOUT_SECONDS = 300


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=GIT_ROOT,
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
    ).stdout


def tracked_text_files() -> list[str]:
    """I file tracciati sotto il package, esclusi i binari.

    L'esclusione passa da `git check-attr`, non da un elenco di estensioni: la
    convenzione su cosa sia binario e' gia' dichiarata in `.gitattributes`, e
    ripeterla qui significherebbe poterla contraddire.
    """
    paths = [
        line
        for line in _git("ls-files", PACKAGE_PREFIX).decode().splitlines()
        if line.strip()
    ]
    result = subprocess.run(
        ["git", "check-attr", "--stdin", "text"],
        cwd=GIT_ROOT,
        input="\n".join(paths).encode(),
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
    ).stdout.decode()

    binary = set()
    for line in result.splitlines():
        if line.count(": ") < 2:
            continue
        path, _attr, value = line.rsplit(": ", 2)
        if value.strip() in ("unset", "false"):
            binary.add(path)
    return [path for path in paths if path not in binary]


def _blob_paths() -> dict[str, set[str]]:
    """Ogni blob dell'object database, con i path sotto cui e' comparso.

    `rev-list --all --objects` associa i blob ai nomi, quindi non serve fissare
    un commit per ritrovare la forma storica di un file: la si ritrova perche'
    e' ancora nell'archivio.
    """
    mapping: dict[str, set[str]] = defaultdict(set)
    for line in _git("rev-list", "--all", "--objects").decode().splitlines():
        sha, _, path = line.partition(" ")
        if path.startswith(PACKAGE_PREFIX):
            mapping[sha].add(path)
    return mapping


def _read_blobs(shas: list[str]) -> dict[str, bytes]:
    """I byte di piu' blob, con un solo processo git.

    Un `cat-file` per blob costava oltre un minuto su questo repository: non e'
    un dettaglio di prestazioni, e' la differenza fra un controllo che sta nella
    suite e uno che verrebbe tolto perche' troppo lento. Uno strumento di audit
    che nessuno esegue non verifica niente.
    """
    if not shas:
        return {}
    stream = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=GIT_ROOT,
        input=("\n".join(shas) + "\n").encode(),
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
    ).stdout

    blobs: dict[str, bytes] = {}
    offset = 0
    while offset < len(stream):
        newline = stream.index(b"\n", offset)
        sha, kind, size = stream[offset:newline].decode().split()
        if kind != "blob":
            raise RuntimeError(f"atteso un blob, ricevuto {kind} per {sha}")
        start = newline + 1
        end = start + int(size)
        blobs[sha] = stream[start:end]
        offset = end + 1  # il newline che git aggiunge dopo il contenuto
    return blobs


def build_index(text_files: set[str]) -> dict[str, tuple[str, str, str]]:
    """digest -> (path, forma, blob). Prima occorrenza vince, forme ordinate.

    Il blob di provenienza fa parte del risultato: dire che un'impronta descrive
    «i byte grezzi» di un file non basta a ritrovarla, perche' quel file ha avuto
    piu' forme nel tempo. Con il blob chiunque puo' rifare la misura da solo.
    """
    index: dict[str, tuple[str, str, str]] = {}

    def record(digest: str, path: str, form: str, blob: str) -> None:
        if digest != _EMPTY_SHA256:
            index.setdefault(digest, (path, form, blob))

    by_blob = {
        sha: sorted(paths & text_files)
        for sha, paths in _blob_paths().items()
        if paths & text_files
    }
    contents = _read_blobs(sorted(by_blob))

    for sha, relevant in by_blob.items():
        blob = contents[sha]
        try:
            lf = POLICY.canonical_lf_bytes(blob)
        except POLICY.LoneCarriageReturnError:
            # Un CR isolato: nessuna conversione lo produce, e i byte grezzi
            # sono l'unica impronta che descrive quella forma.
            for path in relevant:
                record(POLICY.raw_sha256(blob), path, "lone_cr", sha)
            continue
        crlf = lf.replace(b"\n", b"\r\n")
        for path in relevant:
            record(hashlib.sha256(lf).hexdigest(), path, "lf", sha)
            record(hashlib.sha256(crlf).hexdigest(), path, "crlf", sha)
            record(POLICY.raw_sha256(blob), path, "raw", sha)
    return index


def head_blobs() -> dict[str, str]:
    """path -> blob, come HEAD lo conserva."""
    mapping: dict[str, str] = {}
    for line in _git("ls-tree", "-r", "HEAD", "--", PACKAGE_PREFIX).decode().splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            mapping[path] = parts[2]
    return mapping


def discover() -> dict[str, Any]:
    text_files = tracked_text_files()
    as_set = set(text_files)
    index = build_index(as_set)

    at_head = head_blobs()
    artifact_paths = [p for p in text_files if p.endswith(ARTIFACT_SUFFIXES)]
    bodies = _read_blobs(sorted({at_head[p] for p in artifact_paths if p in at_head}))

    references: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for path in artifact_paths:
        body = bodies.get(at_head.get(path, ""), b"")
        for match in sorted({m.decode() for m in _HEX64.findall(body)}):
            hit = index.get(match)
            if hit is None:
                continue
            source, form, blob = hit
            # `lf` e' la forma canonica: quelle referenze stanno gia' bene.
            # Un file che cita se stesso non sta congelando un altro file.
            if form == "lf" or source == path:
                continue
            references[source].append((path, match, form, blob))

    sources: dict[str, Any] = {}
    for source in sorted(references):
        entries = sorted(references[source])
        digests = {digest for _, digest, _, _ in entries}
        if len(digests) != 1:
            raise RuntimeError(
                f"{source} e' citato con {len(digests)} impronte storiche "
                f"diverse: {sorted(digests)}. L'erratum assume una forma "
                f"storica sola per sorgente e va esteso prima di procedere."
            )
        forms = sorted({form for _, _, form, _ in entries})
        blobs = sorted({blob for _, _, _, blob in entries})
        head = at_head[source]
        record = POLICY.HashRecord(
            historical_raw_sha256=entries[0][1],
            canonical_lf_sha256=POLICY.canonical_lf_sha256(
                _read_blobs([head])[head]
            ),
        )
        sources[source.removeprefix(PACKAGE_PREFIX)] = {
            **record.as_dict(),
            "historical_form": forms[0] if len(forms) == 1 else forms,
            # Il blob da cui l'impronta storica si rifa': `git cat-file blob <sha>`
            # la riproduce senza passare da qui.
            "historical_blob": blobs[0] if len(blobs) == 1 else blobs,
            "historical_blob_is_head": blobs == [head],
            "recorded_by": sorted(
                {artifact.removeprefix(PACKAGE_PREFIX) for artifact, _, _, _ in entries}
            ),
        }

    artifacts = sorted(
        {
            artifact.removeprefix(PACKAGE_PREFIX)
            for entries in references.values()
            for artifact, _, _, _ in entries
        }
    )
    return {
        "artifacts": artifacts,
        "counts": {
            "artifacts": len(artifacts),
            "references": sum(len(v) for v in references.values()),
            "sources": len(sources),
        },
        "hash_policy_version": POLICY.POLICY_VERSION,
        "normalization": POLICY.NORMALIZATION,
        "phase": PHASE,
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="non riscrive: esce diverso da zero se l'erratum non e' aggiornato",
    )
    args = parser.parse_args(argv)

    discovered = discover()
    rendered = json.dumps(discovered, ensure_ascii=False, indent=2, sort_keys=True)

    if args.check:
        if not ERRATUM_PATH.exists():
            print(f"erratum assente: {ERRATUM_PATH}", file=sys.stderr)
            return 1
        current = ERRATUM_PATH.read_text(encoding="utf-8").rstrip("\n")
        if current != rendered:
            print("l'erratum non corrisponde a cio' che il repository contiene", file=sys.stderr)
            return 1
        print(json.dumps(discovered["counts"], indent=2, sort_keys=True))
        return 0

    ERRATUM_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERRATUM_PATH.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(f"scritto {ERRATUM_PATH.relative_to(REPO_ROOT)}")
    print(json.dumps(discovered["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
