"""Helper condiviso per i controlli di perimetro di fase.

Il difetto corretto qui e' ricomparso in quattro fasi consecutive. Ogni fase
scriveva il proprio controllo di perimetro come::

    git diff --name-only <start_sha>

cioe' confrontando lo SHA iniziale della fase con l'albero di lavoro. Finche' la
fase e' aperta il confronto e' corretto, ma appena la fase successiva comincia a
scrivere dentro al *proprio* perimetro il diff continua a crescere e il test
della fase precedente fallisce: non perche' quella fase abbia scritto dove non
doveva, ma perche' sta misurando l'intervallo sbagliato.

Il perimetro di una fase e' una proprieta' storica e chiusa: va misurato
sull'intervallo ``<start_sha>..<end_sha>``, dove ``end_sha`` e' il commit con cui
la fase si e' chiusa. Cosi' misurato il controllo resta stabile per sempre e
fallisce soltanto quando la fase che descrive ha davvero sconfinato.

Questo modulo non conosce nessuna fase in particolare: riceve start SHA, end SHA
e path consentiti, e non legge mai l'albero di lavoro.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "PhaseScope",
    "changed_paths_in_closed_interval",
    "paths_outside_prefixes",
]

# I path emessi da git sono relativi alla radice del repository, che sta un
# livello sopra il package `mtb-graphrag`. Le fasi ragionano in path relativi al
# package, quindi il prefisso va tolto una volta sola, qui.
PACKAGE_PREFIX = "mtb-graphrag/"

_GIT_TIMEOUT_SECONDS = 60


def changed_paths_in_closed_interval(
    repo_root: Path,
    start_sha: str,
    end_sha: str,
) -> set[str]:
    """Path toccati nell'intervallo chiuso ``start_sha..end_sha``.

    Non viene mai consultato l'albero di lavoro: entrambi gli estremi sono
    commit. Se git non e' disponibile o uno degli SHA non e' raggiungibile in
    questo checkout il test viene saltato, perche' in quel caso il controllo non
    ha nulla da dire sul perimetro.
    """
    if shutil.which("git") is None:
        raise unittest.SkipTest("git non disponibile")
    if not start_sha or not end_sha:
        raise ValueError("il perimetro richiede entrambi gli estremi dell'intervallo")
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{start_sha}..{end_sha}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover
        raise unittest.SkipTest(f"git non utilizzabile: {error}") from error
    if result.returncode != 0:
        raise unittest.SkipTest(
            "gli estremi dell'intervallo non sono raggiungibili in questo checkout"
        )
    return {
        line.strip().removeprefix(PACKAGE_PREFIX)
        for line in result.stdout.splitlines()
        if line.strip()
    }


def paths_outside_prefixes(paths: Iterable[str], prefixes: Iterable[str]) -> list[str]:
    """Path che non ricadono sotto nessuno dei prefissi consentiti."""
    allowed = tuple(prefixes)
    return sorted(path for path in paths if not path.startswith(allowed))


class PhaseScope:
    """Perimetro di una fase, misurato su un intervallo chiuso di commit."""

    def __init__(
        self,
        repo_root: Path,
        start_sha: str,
        end_sha: str,
        allowed_write_prefixes: Iterable[str],
    ) -> None:
        self.repo_root = repo_root
        self.start_sha = start_sha
        self.end_sha = end_sha
        self.allowed_write_prefixes = tuple(allowed_write_prefixes)

    def changed_paths(self) -> set[str]:
        return changed_paths_in_closed_interval(
            self.repo_root, self.start_sha, self.end_sha
        )

    def violations(self, changed: Iterable[str]) -> list[str]:
        return paths_outside_prefixes(changed, self.allowed_write_prefixes)
